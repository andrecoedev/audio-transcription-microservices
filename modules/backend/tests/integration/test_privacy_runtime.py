"""Real PostgreSQL locks, deletion receipts, cascades and no resurrection."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
import secrets

import pytest
from fastapi import HTTPException, Request
from sqlalchemy import inspect
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from pathlib import Path

from src.models import AccountDeletion, AuditEvent, FirebaseIdentity, Meeting, MeetingIntelligence, Transcription, TranscriptionOwnership, User, UserProviderCredential
from src.routers.privacy import DeleteAccountInput, delete_account
from src.security import TokenData, get_password_hash
from src.services import privacy, account_deletion
from src.services.transcription_entitlements import access
from src.workers import meeting_intelligence_worker

pytestmark = pytest.mark.postgres


def seed(factory):
    password = secrets.token_urlsafe(16)
    with factory() as db:
        user = User(username="privacy-synthetic", email="privacy@example.test", hashed_password=get_password_hash(password))
        db.add(user)
        db.flush()
        identifier = user.id
        transcription = Transcription(filename="private.wav", original_filename="meeting.wav", file_size_mb=1,
            duration_seconds=10, transcription_model="whisper", status="completed", segments=[])
        db.add(transcription)
        db.flush()
        resource = transcription.id
        db.add(TranscriptionOwnership(transcription_id=resource, user_id=identifier, owner_sub=user.username))
        db.add(Meeting(id=resource, title="Synthetic", language="pt"))
        db.add(FirebaseIdentity(project_id="synthetic-project", uid="synthetic-uid", user_id=identifier))
        db.add(UserProviderCredential(id=str(uuid4()), user_id=identifier, provider="gemini", ciphertext="synthetic-only"))
        db.commit()
    return identifier, resource, password


def test_erasure_nowait_rejects_concurrent_admission_and_then_cascades(postgres_session_factory, monkeypatch):
    identifier, resource, password = seed(postgres_session_factory)
    monkeypatch.setattr("src.routers.privacy.enforce_rate_limit", lambda *_args: None)
    monkeypatch.setattr(account_deletion, "ensure_no_legacy_minutes_jobs", lambda _ids: None)
    monkeypatch.setattr(privacy, "ensure_no_legacy_minutes_jobs", lambda _ids: None)
    monkeypatch.setattr(account_deletion, "delete_firebase_identity", lambda *_args: None)
    held, release = Event(), Event()
    def admission():
        with postgres_session_factory() as db:
            db.query(User).filter_by(id=identifier).with_for_update(key_share=True).one()
            held.set()
            assert release.wait(10)
            db.rollback()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(admission)
        assert held.wait(10)
        try:
            with postgres_session_factory() as db:
                with pytest.raises(HTTPException) as error:
                    delete_account(DeleteAccountInput(confirmation="EXCLUIR", password=password),
                        Request({"type": "http", "method": "DELETE", "path": "/account", "headers": [], "query_string": b""}),
                        db=db, principal=TokenData(user_id=identifier), token="synthetic")
                assert error.value.status_code == 409
                assert db.get(User, identifier) is not None
        finally:
            release.set()
        future.result(timeout=10)
    with postgres_session_factory() as db:
        result = privacy.erase_user_data(db, db.get(User, identifier))
        assert result.identity_cleanup_pending is False
        assert db.get(User, identifier) is None
        assert db.get(Transcription, resource) is None
        assert db.get(Meeting, resource) is None
        assert db.query(UserProviderCredential).count() == 0
        assert db.query(FirebaseIdentity).count() == 0
        assert db.query(AccountDeletion).one().firebase_uid is None
        assert db.query(AuditEvent).filter_by(event="user.data_deleted").one().actor_user_id is None
        with pytest.raises(HTTPException) as error:
            access(db, identifier, lock=True)
        assert error.value.status_code == 403


def test_worker_does_not_recreate_deleted_analysis(postgres_session_factory, monkeypatch):
    identifier, resource, _password = seed(postgres_session_factory)
    with postgres_session_factory() as db:
        row = MeetingIntelligence(meeting_id=resource, revision=1, schema_version="1", provider="gemini",
            model="synthetic", status="completed", source_metadata={}, input_fingerprint="synthetic", result={})
        db.add(row)
        db.commit()
        revision = row.id
    monkeypatch.setattr(privacy, "ensure_no_legacy_minutes_jobs", lambda _ids: None)
    monkeypatch.setattr(account_deletion, "delete_firebase_identity", lambda *_args: None)
    with postgres_session_factory() as db:
        privacy.erase_user_data(db, db.get(User, identifier))
    monkeypatch.setattr(meeting_intelligence_worker, "SessionLocal", postgres_session_factory)
    monkeypatch.setattr(meeting_intelligence_worker, "get_provider", lambda: pytest.fail("Deleted revision must not call a provider"))
    assert meeting_intelligence_worker.process_intelligence_job(revision)["status"] == "already_claimed_or_deleted"
    assert meeting_intelligence_worker._complete(revision, {}) is False
    with postgres_session_factory() as db:
        assert db.query(Meeting).count() == 0
        assert db.query(MeetingIntelligence).count() == 0


def test_account_erasure_migration_is_additive_and_guards_receipts(postgres_engine):
    # Never downgrade the runtime schema: exercise this revision in a fresh schema.
    schema = "privacy_migration_" + uuid4().hex
    backend = Path(__file__).resolve().parents[2]
    revision = ScriptDirectory.from_config(Config(str(backend / "alembic.ini"))).get_revision("20261013_0015").module
    from sqlalchemy import text
    try:
        with postgres_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            with Operations.context(MigrationContext.configure(connection)):
                revision.upgrade()
                assert "account_deletions" in inspect(connection).get_table_names(schema=schema)
                revision.downgrade()
                revision.upgrade()
                connection.execute(text("INSERT INTO account_deletions (id, deleted_user_id) VALUES (:id, 999)"), {"id": str(uuid4())})
                with pytest.raises(RuntimeError, match="Preserve account deletion"):
                    revision.downgrade()
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
