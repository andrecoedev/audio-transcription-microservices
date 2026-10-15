from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from fastapi import HTTPException

from src.models import PlatformProviderBudget, PlatformProviderCall, Transcription
from src.services.platform_budget import reserve_platform_call, begin_platform_call
from tests.platform_helpers import configure_platform, confirm_test_balance


def test_concurrent_workers_respect_single_external_slot(postgres_session_factory, monkeypatch):
    configure_platform(monkeypatch)
    with postgres_session_factory() as db:
        confirm_test_balance(db)
        ids = []
        for index in range(2):
            row = Transcription(filename=f"synthetic-{index}.wav", original_filename="synthetic.wav",
                file_size_mb=0.1, duration_seconds=0, transcription_model="assemblyai", status="queued")
            db.add(row)
            db.flush()
            ids.append(row.id)
            reserve_platform_call(db, row.id, "local")
        db.commit()
    barrier = Barrier(2)

    def attempt(tid):
        with postgres_session_factory() as db:
            barrier.wait(timeout=10)
            try:
                begin_platform_call(db, tid, duration_seconds=60)
                return "attempted"
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, ids))
    assert sorted(results, key=str) == sorted(["attempted", 429], key=str)
    with postgres_session_factory() as db:
        assert db.query(PlatformProviderCall).filter_by(state="attempted").count() == 1
        assert db.get(PlatformProviderBudget, "assemblyai").reserved_cents == Decimal("4.21666668")


def test_new_migration_cannot_drop_manual_reconciliation_of_legacy_call(
    postgres_engine, postgres_session_factory, monkeypatch
):
    from datetime import datetime, timezone
    with postgres_session_factory() as db:
        db.add(PlatformProviderBudget(provider="assemblyai", limit_cents=200, reserved_cents=0))
        db.flush()
        db.add(PlatformProviderCall(provider="assemblyai", context="local", credential_source="platform",
            reserved_cents=17, state="attempted", provider_status="not_submitted",
            settled_at=datetime.now(timezone.utc), released_at=datetime.now(timezone.utc)))
        db.commit()
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    migration = ScriptDirectory.from_config(config).get_revision("20261015_0017").module
    with postgres_engine.begin() as connection:
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError, match="Beta financial evidence"):
            migration.downgrade()


def test_initial_round_cannot_configure_more_than_five_invited_users(monkeypatch):
    from pydantic import ValidationError
    from src.config import Settings
    with pytest.raises(ValidationError):
        Settings(_env_file=None, AAI_BETA_MAX_USERS=6)
