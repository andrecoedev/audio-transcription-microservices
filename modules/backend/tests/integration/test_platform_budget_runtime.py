from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from fastapi import HTTPException
from sqlalchemy import inspect, text

from src.models import PlatformProviderBudget, PlatformProviderCall, Transcription
from src.services import platform_budget
from src.services.platform_budget import reserve_platform_call


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _seed_transcription(factory, filename):
    db = factory()
    try:
        row = Transcription(
            filename=filename,
            original_filename=filename,
            file_size_mb=0.1,
            duration_seconds=600,
            transcription_model="assemblyai",
            status="queued",
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def test_concurrent_platform_reservations_cannot_exceed_budget(
    postgres_engine, postgres_session_factory, monkeypatch
):
    monkeypatch.setattr(platform_budget.settings, "AAI_PLATFORM_ENABLED", True)
    monkeypatch.setattr(platform_budget.settings, "AAI_PLATFORM_BUDGET_CENTS", 17)
    monkeypatch.setattr(platform_budget.settings, "AAI_MAX_AUDIO_SECONDS", 600)
    transcription_ids = [
        _seed_transcription(postgres_session_factory, f"parallel-{index}.wav")
        for index in range(2)
    ]
    barrier = Barrier(2)

    def reserve(transcription_id):
        db = postgres_session_factory()
        try:
            barrier.wait(timeout=10)
            reserve_platform_call(db, transcription_id, "guest")
            db.commit()
            return "reserved"
        except HTTPException as exc:
            db.rollback()
            return exc.status_code
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(reserve, transcription_ids))

    assert sorted(outcomes, key=str) == sorted(["reserved", 429], key=str)
    db = postgres_session_factory()
    try:
        budget = db.get(PlatformProviderBudget, "assemblyai")
        calls = db.query(PlatformProviderCall).all()
        assert budget.reserved_cents == 17
        assert len(calls) == 1
        assert calls[0].reserved_cents == 17
        assert calls[0].transcription_id in transcription_ids
    finally:
        db.close()


def test_budget_migration_downgrade_refuses_to_drop_spending_records(
    postgres_engine, postgres_session_factory, monkeypatch
):
    db = postgres_session_factory()
    row = Transcription(
        filename="migration-budget.wav",
        original_filename="migration-budget.wav",
        file_size_mb=0.1,
        duration_seconds=600,
        transcription_model="assemblyai",
        status="queued",
    )
    db.add(row)
    db.flush()
    db.add(PlatformProviderBudget(provider="assemblyai", limit_cents=17, reserved_cents=17))
    db.flush()
    db.add(
        PlatformProviderCall(
            transcription_id=row.id,
            provider="assemblyai",
            context="guest",
            credential_source="platform",
            reserved_cents=17,
            state="attempted",
        )
    )
    db.commit()
    db.close()

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision("20261002_0008").module
    with postgres_engine.begin() as connection:
        head_before = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        monkeypatch.setattr(
            revision,
            "op",
            Operations(MigrationContext.configure(connection)),
        )
        with pytest.raises(RuntimeError, match="Preserve platform spending records"):
            revision.downgrade()

        table_names = set(inspect(connection).get_table_names())
        assert "platform_provider_budgets" in table_names
        assert "platform_provider_calls" in table_names
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar() == head_before
