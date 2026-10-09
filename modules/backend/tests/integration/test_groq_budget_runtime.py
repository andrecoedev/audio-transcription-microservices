"""PostgreSQL concurrency and migration guards for platform Groq admission."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from decimal import Decimal
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
    BetaAccessGrant, IntelligencePlatformCall, Meeting, MeetingIntelligence,
    PlatformProviderBudget, Transcription, TranscriptionOwnership, User,
    UserProviderPreferences,
)
from src.services.groq_budget import reserve_groq_call
from src.services.meeting_intelligence import snapshot, fingerprint
from src.services.transcription_entitlements import CAPABILITIES


pytestmark = pytest.mark.postgres
BACKEND_ROOT = Path(__file__).resolve().parents[2]
CONTEXT = {"language": "pt", "speakers": [], "segments": [{"order": 0, "start": 0,
           "end": 1, "speaker": "SPEAKER_00", "text": "Síntese sintética."}]}


def _configure(monkeypatch, *, budget_cents=100, active=3):
    policy = {"monthly_usagi_seconds": 36000, "max_audio_seconds": 600,
              "max_stored_bytes": 1024 * 1024 * 1024, "max_queued_jobs": 100,
              "max_processing_jobs": 10}
    monkeypatch.setattr(settings, "PLAN_POLICIES_JSON",
        json.dumps({name: policy for name in ("free", "starter", "business", "beta")}))
    monkeypatch.setattr(settings, "GROQ_PLATFORM_ENABLED", True)
    monkeypatch.setattr(settings, "GROQ_API_KEY_CONFIGURED", True)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "synthetic-postgres-key")
    monkeypatch.setattr(settings, "GROQ_PLATFORM_BUDGET_CENTS", budget_cents)
    # Synthetic ceilings keep this short fixture's hold at exactly one cent.
    monkeypatch.setattr(settings, "GROQ_INPUT_USD_PER_MILLION", Decimal("0.5"))
    monkeypatch.setattr(settings, "GROQ_OUTPUT_USD_PER_MILLION", Decimal("0.5"))
    monkeypatch.setattr(settings, "GROQ_MAX_ACTIVE_PER_USER", active)
    monkeypatch.setattr(settings, "GROQ_MAX_PROCESSING_PER_USER", 1)


def _seed_user(db, label):
    user = User(username=f"groq-{label}-{uuid4().hex}",
                email=f"groq-{uuid4().hex}@example.invalid", hashed_password="synthetic-fixture")
    db.add(user)
    db.flush()
    db.add(BetaAccessGrant(id=str(uuid4()), user_id=user.id,
        capabilities=sorted(CAPABILITIES),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    db.flush()
    return user.id


def _seed_intelligence(db, user_id, label):
    transcription = Transcription(filename=f"{label}.wav", original_filename=f"{label}.wav",
        file_size_mb=0.001, duration_seconds=1, transcription_model="whisper",
        segments=CONTEXT["segments"], status="completed")
    db.add(transcription)
    db.flush()
    db.add(TranscriptionOwnership(transcription_id=transcription.id,
        owner_sub=f"user:{user_id}", user_id=user_id))
    meeting = Meeting(id=transcription.id, title="Synthetic meeting", language="pt")
    db.add(meeting)
    db.flush()
    row = MeetingIntelligence(meeting_id=meeting.id, revision=1, schema_version="1",
        provider="groq", model=settings.GROQ_MODEL, credential_source="platform",
        status="failed", source_metadata={"language": "pt", "speakers": []},
        input_fingerprint="a" * 64)
    db.add(row)
    db.flush()
    return row.id


def _reserve(factory, user_id, intelligence_id, barrier):
    db = factory()
    try:
        barrier.wait(timeout=15)
        db.get(MeetingIntelligence, intelligence_id).status = "pending"
        db.flush()
        call = reserve_groq_call(db, user_id, intelligence_id, CONTEXT)
        db.commit()
        return ("reserved", call.reserved_cents)
    except HTTPException as exc:
        db.rollback()
        return (exc.status_code, None)
    finally:
        db.close()


def test_concurrent_same_user_admissions_observe_max_active_limit(
    postgres_session_factory, monkeypatch
):
    _configure(monkeypatch, active=1)
    db = postgres_session_factory()
    try:
        user_id = _seed_user(db, "same-user")
        intelligence_ids = [_seed_intelligence(db, user_id, f"same-{index}") for index in range(2)]
        db.add(PlatformProviderBudget(provider="groq", limit_cents=100, reserved_cents=0))
        db.commit()
    finally:
        db.close()

    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda intelligence_id: _reserve(
            postgres_session_factory, user_id, intelligence_id, barrier), intelligence_ids))
    assert sorted((result[0] for result in outcomes), key=str) == sorted(["reserved", 429], key=str)

    db = postgres_session_factory()
    try:
        calls = db.query(IntelligencePlatformCall).all()
        assert len(calls) == 1
        assert calls[0].intelligence_id in intelligence_ids
    finally:
        db.close()


def test_concurrent_different_users_cannot_exceed_one_cent_global_budget(
    postgres_session_factory, monkeypatch
):
    _configure(monkeypatch, budget_cents=1)
    db = postgres_session_factory()
    try:
        user_ids = [_seed_user(db, f"global-{index}") for index in range(2)]
        intelligence_ids = [_seed_intelligence(db, user_id, f"global-{index}")
                            for index, user_id in enumerate(user_ids)]
        db.add(PlatformProviderBudget(provider="groq", limit_cents=1, reserved_cents=0))
        db.commit()
    finally:
        db.close()

    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda item: _reserve(
            postgres_session_factory, item[0], item[1], barrier), zip(user_ids, intelligence_ids)))
    assert sorted((result[0] for result in outcomes), key=str) == sorted(["reserved", 429], key=str)

    db = postgres_session_factory()
    try:
        budget = db.get(PlatformProviderBudget, "groq")
        calls = db.query(IntelligencePlatformCall).all()
        assert budget.reserved_cents == 1
        assert len(calls) == 1 and calls[0].intelligence_id in intelligence_ids
    finally:
        db.close()


def test_groq_reservation_is_idempotent_for_same_operation(postgres_session_factory, monkeypatch):
    _configure(monkeypatch)
    db = postgres_session_factory()
    try:
        user_id = _seed_user(db, "idempotent")
        intelligence_id = _seed_intelligence(db, user_id, "idempotent")
        db.add(PlatformProviderBudget(provider="groq", limit_cents=100, reserved_cents=0))
        db.flush()
        first = reserve_groq_call(db, user_id, intelligence_id, CONTEXT)
        amount = first.reserved_cents
        second = reserve_groq_call(db, user_id, intelligence_id, CONTEXT)
        db.commit()
        assert second.id == first.id
        assert second.reserved_cents == amount
        assert db.get(PlatformProviderBudget, "groq").reserved_cents == amount
        assert db.query(IntelligencePlatformCall).count() == 1
    finally:
        db.close()


def test_groq_migration_downgrade_guard_preserves_explicit_preferences(
    postgres_engine, postgres_session_factory, monkeypatch
):
    db = postgres_session_factory()
    try:
        user_id = _seed_user(db, "migration")
        db.add(UserProviderPreferences(user_id=user_id, intelligence_provider="groq"))
        db.commit()
    finally:
        db.close()


    scripts = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))
    revision = scripts.get_revision("20261009_0014").module
    with postgres_engine.begin() as connection:
        head_before = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        monkeypatch.setattr(revision, "op", Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError, match="Resolve explicit Groq preferences"):
            revision.downgrade()
        assert "intelligence_platform_calls" in set(inspect(connection).get_table_names())
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == head_before
    with postgres_session_factory() as db:
        assert db.get(UserProviderPreferences, user_id).intelligence_provider == "groq"


def test_groq_real_rq_preserves_result_after_ephemeral_job_removal(postgres_session_factory, monkeypatch):
    from redis import Redis
    from rq import Queue, SimpleWorker
    from src.routers import meeting_intelligence as router
    from src.security import TokenData
    from src.workers import meeting_intelligence_worker as worker

    if not os.getenv("REDIS_URL"):
        pytest.skip("REDIS_URL required")
    _configure(monkeypatch)
    db = postgres_session_factory()
    try:
        user_id = _seed_user(db, "real-rq")
        intelligence_id = _seed_intelligence(db, user_id, "real-rq")
        row = db.get(MeetingIntelligence, intelligence_id)
        metadata, segments = snapshot(row.meeting)
        row.source_metadata = metadata
        row.input_fingerprint = fingerprint(metadata, segments)
        row.status = "pending"
        meeting_id = row.meeting_id
        reserve_groq_call(db, user_id, intelligence_id, {**metadata, "segments": segments})
        db.commit()
    finally:
        db.close()
    calls = []
    class SyntheticProvider:
        def generate(self, _context):
            calls.append(True)
            return json.dumps({"schema_version": "1", "summary": "Síntese sintética.",
                "topics": [], "decisions": [], "action_items": [], "open_questions": []})
    monkeypatch.setattr(worker, "SessionLocal", postgres_session_factory)
    monkeypatch.setattr(worker, "get_provider", lambda **_kwargs: SyntheticProvider())
    connection = Redis.from_url(os.environ["REDIS_URL"])
    queue = Queue("groq-rq-" + uuid4().hex, connection=connection)
    job = queue.enqueue("src.workers.meeting_intelligence_worker.process_intelligence_job", intelligence_id)
    assert SimpleWorker([queue], connection=connection).work(burst=True, logging_level="WARNING")
    job.refresh()
    assert job.get_status() == "finished"
    assert worker.process_intelligence_job(intelligence_id)["status"] == "already_claimed_or_deleted"
    assert calls == [True]
    job.delete()
    with postgres_session_factory() as db:
        result = router.result(meeting_id, revision=None, db=db,
            user=TokenData(user_id=user_id, username="real-rq"))
        assert result["content"]["summary"] == "Síntese sintética."
        assert result["provider"] == "groq"
