from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.models import GuestSession, Transcription, TranscriptionOwnership, User
from src.security import TokenData, create_access_token
from src.services.guest_sessions import claim_guest_results

pytestmark = pytest.mark.postgres


def test_competing_accounts_cannot_both_claim_guest_results(postgres_session_factory):
    db = postgres_session_factory()
    db.add_all([User(id=i, username=f"user{i}", email=f"user{i}@example.test", hashed_password="unused",
                     registration_source="public") for i in (1, 2)])
    guest = GuestSession(id=str(uuid4()), expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    db.add(guest)
    db.flush()
    row = Transcription(filename="synthetic.wav", original_filename="synthetic.wav", file_size_mb=1,
                        duration_seconds=1, transcription_model="whisper", segments=[], status="completed")
    db.add(row)
    db.flush()
    db.add(TranscriptionOwnership(transcription_id=row.id, owner_sub=f"guest:{guest.id}", guest_session_id=guest.id))
    token = create_access_token({"sub": guest.id, "purpose": "guest"})
    db.commit()
    db.close()
    barrier = Barrier(2)
    def claim(user_id):
        session = postgres_session_factory()
        try:
            barrier.wait()
            result = claim_guest_results(session, token, TokenData(user_id=user_id, username=f"user{user_id}"))
            return result["transferred"]
        except HTTPException as exc:
            session.rollback()
            return exc.status_code
        finally:
            session.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, (1, 2)))
    assert sorted(results) == [1, 403]
    db = postgres_session_factory()
    owner = db.query(TranscriptionOwnership).one()
    assert owner.user_id in {1, 2} and owner.guest_session_id is None
    assert db.query(GuestSession).one().claimed_by_user_id == owner.user_id
    db.close()


def test_guest_upload_reservation_is_atomic(postgres_session_factory):
    db = postgres_session_factory()
    guest_id = str(uuid4())
    db.add(GuestSession(id=guest_id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    db.commit()
    db.close()
    barrier = Barrier(2)
    def reserve(_):
        db = postgres_session_factory()
        try:
            barrier.wait()
            count = db.query(GuestSession).filter(GuestSession.id == guest_id, GuestSession.jobs_created < 1).update(
                {GuestSession.jobs_created: GuestSession.jobs_created + 1})
            db.commit()
            return count
        finally:
            db.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, (1, 2))) == [0, 1]


@pytest.mark.parametrize("context", ["public_account", "guest_ownership"])
def test_guest_migration_downgrade_preserves_existing_context(postgres_session_factory, postgres_engine, monkeypatch, context):
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect, text

    db = postgres_session_factory()
    if context == "public_account":
        db.add(User(username="synthetic", email="synthetic@example.test", hashed_password="unused", registration_source="public"))
    else:
        guest = GuestSession(id=str(uuid4()), expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        row = Transcription(filename="synthetic.wav", original_filename="synthetic.wav", file_size_mb=1,
                            duration_seconds=1, transcription_model="whisper", segments=[], status="completed")
        db.add_all([guest, row])
        db.flush()
        db.add(TranscriptionOwnership(transcription_id=row.id, owner_sub=f"guest:{guest.id}", guest_session_id=guest.id))
    db.commit()
    db.close()
    revision = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("20261002_0007").module
    with postgres_engine.begin() as connection:
        monkeypatch.setattr(revision, "op", Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError, match="preservation plan|Claim or explicitly erase"):
            revision.downgrade()
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "20261002_0007"
        assert "guest_sessions" in inspect(connection).get_table_names()
        assert "registration_source" in {column["name"] for column in inspect(connection).get_columns("users")}
