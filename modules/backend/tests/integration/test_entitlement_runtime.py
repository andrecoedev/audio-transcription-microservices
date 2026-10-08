"""Real PostgreSQL coverage for account plans and transcription reservations."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from fastapi import HTTPException
from sqlalchemy import inspect, text

from src.config import settings
from src.models import (
    BetaAccessGrant,
    Transcription,
    TranscriptionJob,
    TranscriptionOwnership,
    TranscriptionReservation,
    User,
)
from src.services.transcription_entitlements import claim_reservation, plan_view, reserve_transcription


pytestmark = pytest.mark.postgres
BACKEND_ROOT = Path(__file__).resolve().parents[2]
LOCAL_SELECTION = {"provider": "whisper", "credential_source": "none"}
BYOK_SELECTION = {"provider": "assemblyai", "credential_source": "user"}


def _set_policy(monkeypatch, **overrides):
    policy = {
        "monthly_usagi_seconds": 600,
        "max_audio_seconds": 60,
        "max_stored_bytes": 10_000,
        "max_queued_jobs": 10,
        "max_processing_jobs": 10,
    }
    policy.update(overrides)
    monkeypatch.setattr(
        settings,
        "PLAN_POLICIES_JSON",
        json.dumps({name: policy for name in ("free", "starter", "business", "beta")}),
    )
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_ENABLED", True)
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_HOMOLOGATED", True)


def _seed_user(factory, *, plan="free"):
    db = factory()
    try:
        user = User(
            username=f"entitlement-{uuid4().hex}",
            email=f"entitlement-{uuid4().hex}@example.invalid",
            hashed_password="synthetic-fixture",
            plan=plan,
        )
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def _add_job(db, user_id, label, *, provider="whisper", credential_source="none"):
    transcription = Transcription(
        filename=f"{label}.wav",
        original_filename=f"{label}.wav",
        file_size_mb=0.001,
        duration_seconds=1,
        transcription_model=provider,
        segments=[],
        status="queued",
    )
    db.add(transcription)
    db.flush()
    db.add(
        TranscriptionOwnership(
            transcription_id=transcription.id,
            owner_sub=f"user:{user_id}",
            user_id=user_id,
        )
    )
    db.add(
        TranscriptionJob(
            transcription_id=transcription.id,
            input_path=f"{label}.wav",
            transcription_model=provider,
            credential_source=credential_source,
            status="queued",
        )
    )
    db.flush()
    return transcription.id


def _reserve(db, user_id, transcription_id, selection, size_bytes=10):
    return reserve_transcription(
        db,
        user_id,
        transcription_id,
        selection,
        size_bytes,
        f"object:entitlement-test-{transcription_id}",
    )


def test_entitlement_migration_defaults_and_downgrade_guards_preserve_resources(
    postgres_engine, monkeypatch
):
    schema = "entitlement_migration_" + uuid4().hex
    scripts = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))
    revision = scripts.get_revision("20261008_0013").module

    try:
        with postgres_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            connection.execute(
                text("CREATE TABLE users (id integer PRIMARY KEY, username varchar(50), email varchar(255))")
            )
            connection.execute(text("CREATE TABLE transcriptions (id integer PRIMARY KEY)"))
            connection.execute(
                text("INSERT INTO users (id, username, email) VALUES (1, 'preserved-user', 'preserved@example.invalid')")
            )
            connection.execute(text("INSERT INTO transcriptions (id) VALUES (77)"))

            monkeypatch.setattr(
                revision, "op", Operations(MigrationContext.configure(connection))
            )
            revision.upgrade()

            user_columns = {column["name"] for column in inspect(connection).get_columns("users")}
            assert "plan" in user_columns
            assert connection.execute(text("SELECT plan FROM users WHERE id = 1")).scalar() == "free"
            assert connection.execute(text("SELECT count(*) FROM transcriptions WHERE id = 77")).scalar() == 1
            connection.execute(
                text("INSERT INTO users (id, username, email) VALUES (2, 'new-user', 'new@example.invalid')")
            )
            assert connection.execute(text("SELECT plan FROM users WHERE id = 2")).scalar() == "free"

            now = datetime.now(timezone.utc)
            connection.execute(
                text("INSERT INTO beta_access_grants (id, user_id, capabilities, expires_at) "
                     "VALUES ('grant-1', 1, '[]', :expires_at)"),
                {"expires_at": now + timedelta(hours=1)},
            )
            connection.execute(
                text("INSERT INTO transcription_reservations "
                     "(id, operation_key, transcription_id, user_id, period_start, source, provider, "
                     "credential_source, state, reserved_seconds, stored_bytes, input_reference) "
                     "VALUES ('reservation-1', 'operation-1', 77, 1, :period_start, 'usagi', 'whisper', "
                     "'none', 'queued', 30, 10, 'object:preserved')"),
                {"period_start": now.date().replace(day=1)},
            )

            with pytest.raises(RuntimeError, match="Preserve beta access grants"):
                revision.downgrade()
            assert "beta_access_grants" in inspect(connection).get_table_names()
            assert "transcription_reservations" in inspect(connection).get_table_names()
            assert connection.execute(text("SELECT username FROM users WHERE id = 1")).scalar() == "preserved-user"
            assert connection.execute(text("SELECT count(*) FROM transcriptions WHERE id = 77")).scalar() == 1

            connection.execute(text("DELETE FROM beta_access_grants"))
            with pytest.raises(RuntimeError, match="Preserve transcription reservations"):
                revision.downgrade()
            connection.execute(text("DELETE FROM transcription_reservations"))
            connection.execute(text("UPDATE users SET plan = 'starter' WHERE id = 2"))
            with pytest.raises(RuntimeError, match="Move all accounts to the free plan"):
                revision.downgrade()
            assert "plan" in {column["name"] for column in inspect(connection).get_columns("users")}

            connection.execute(text("UPDATE users SET plan = 'free' WHERE id = 2"))
            revision.downgrade()
            table_names = set(inspect(connection).get_table_names())
            assert "beta_access_grants" not in table_names
            assert "transcription_reservations" not in table_names
            assert "plan" not in {column["name"] for column in inspect(connection).get_columns("users")}
            assert connection.execute(text("SELECT username FROM users WHERE id = 1")).scalar() == "preserved-user"
            assert connection.execute(text("SELECT count(*) FROM transcriptions WHERE id = 77")).scalar() == 1
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


@pytest.mark.parametrize(
    ("dimension", "overrides", "size_bytes", "expected_detail"),
    [
        ("quota", {"monthly_usagi_seconds": 60, "max_audio_seconds": 60}, 10,
         "franquia mensal"),
        ("queue", {"max_queued_jobs": 1}, 10, "fila"),
        ("storage", {"max_stored_bytes": 10}, 10, "armazenamento"),
    ],
)
def test_concurrent_reservations_admit_only_one_against_each_limit(
    postgres_session_factory, monkeypatch, dimension, overrides, size_bytes, expected_detail
):
    _set_policy(monkeypatch, **overrides)
    user_id = _seed_user(postgres_session_factory)
    barrier = Barrier(2)

    def upload(index):
        db = postgres_session_factory()
        try:
            transcription_id = _add_job(db, user_id, f"parallel-{dimension}-{index}")
            barrier.wait(timeout=10)
            reservation = _reserve(db, user_id, transcription_id, LOCAL_SELECTION, size_bytes)
            db.commit()
            return ("reserved", reservation.id, transcription_id)
        except HTTPException as exc:
            db.rollback()
            return (exc.status_code, exc.detail, None)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(upload, (1, 2)))

    admitted = [outcome for outcome in outcomes if outcome[0] == "reserved"]
    rejected = [outcome for outcome in outcomes if outcome[0] == 429]
    assert len(admitted) == 1
    assert len(rejected) == 1
    assert expected_detail in rejected[0][1]

    db = postgres_session_factory()
    try:
        reservations = db.query(TranscriptionReservation).filter_by(user_id=user_id).all()
        assert len(reservations) == 1
        assert reservations[0].transcription_id == admitted[0][2]
        assert db.query(TranscriptionJob).filter_by(status="queued").count() == 1
    finally:
        db.close()


def test_byok_reservations_do_not_consume_usagi_monthly_quota(postgres_session_factory, monkeypatch):
    _set_policy(monkeypatch, monthly_usagi_seconds=0, max_audio_seconds=60)
    user_id = _seed_user(postgres_session_factory, plan="starter")
    db = postgres_session_factory()
    try:
        ids = [_add_job(db, user_id, f"byok-{index}", provider="assemblyai", credential_source="user")
               for index in (1, 2)]
        holds = [_reserve(db, user_id, transcription_id, BYOK_SELECTION, 10) for transcription_id in ids]
        db.commit()

        assert {hold.source for hold in holds} == {"byok"}
        assert {hold.reserved_seconds for hold in holds} == {60}
        view = plan_view(db, user_id)
        assert view["quota"]["limit_seconds"] == 0
        assert view["quota"]["reserved_seconds"] == "0"
        assert view["byok"]["pending_seconds"] == "120.000"
    finally:
        db.close()


def test_concurrent_processing_claims_respect_single_slot(postgres_session_factory, monkeypatch):
    _set_policy(monkeypatch, max_processing_jobs=1)
    user_id = _seed_user(postgres_session_factory)
    db = postgres_session_factory()
    try:
        transcription_ids = [_add_job(db, user_id, f"claim-{index}") for index in (1, 2)]
        for transcription_id in transcription_ids:
            _reserve(db, user_id, transcription_id, LOCAL_SELECTION)
        db.commit()
    finally:
        db.close()

    barrier = Barrier(2)

    def claim(transcription_id):
        session = postgres_session_factory()
        try:
            changed = session.query(TranscriptionJob).filter_by(
                transcription_id=transcription_id, status="queued"
            ).update({TranscriptionJob.status: "processing"})
            assert changed == 1
            barrier.wait(timeout=10)
            claim_reservation(session, transcription_id)
            session.commit()
            return ("claimed", transcription_id)
        except HTTPException as exc:
            session.rollback()
            return (exc.status_code, transcription_id)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(claim, transcription_ids))

    assert sum(outcome[0] == "claimed" for outcome in outcomes) == 1
    assert sum(outcome[0] == 429 for outcome in outcomes) == 1
    db = postgres_session_factory()
    try:
        assert db.query(TranscriptionJob).filter_by(status="processing").count() == 1
        assert db.query(TranscriptionReservation).filter_by(state="processing").count() == 1
    finally:
        db.close()


def test_concurrent_identical_operation_retries_return_one_reservation(
    postgres_session_factory, monkeypatch
):
    _set_policy(monkeypatch)
    user_id = _seed_user(postgres_session_factory)
    db = postgres_session_factory()
    try:
        transcription = Transcription(
            filename="same-operation.wav",
            original_filename="same-operation.wav",
            file_size_mb=0,
            duration_seconds=1,
            transcription_model="whisper",
            segments=[],
            status="queued",
        )
        db.add(transcription)
        db.commit()
        transcription_id = transcription.id
    finally:
        db.close()

    barrier = Barrier(2)

    def retry(_index):
        session = postgres_session_factory()
        try:
            barrier.wait(timeout=10)
            row = _reserve(session, user_id, transcription_id, LOCAL_SELECTION)
            session.commit()
            return row.id
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        reservation_ids = list(executor.map(retry, (1, 2)))

    assert reservation_ids[0] == reservation_ids[1]
    db = postgres_session_factory()
    try:
        rows = db.query(TranscriptionReservation).filter_by(
            operation_key=f"transcription:{transcription_id}"
        ).all()
        assert len(rows) == 1
        assert rows[0].id == reservation_ids[0]
    finally:
        db.close()
