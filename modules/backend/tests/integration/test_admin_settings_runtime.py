"""Real PostgreSQL serialization and reversible schema; no provider requests."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import pytest
from fastapi import HTTPException
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from src.models import AuditEvent, PlatformProviderBudget
from src.services.beta_settings import initialize_policy, read_policy, update_policy

pytestmark = pytest.mark.postgres


def test_simultaneous_admin_edits_have_one_winner_and_one_audit(postgres_session_factory):
    with postgres_session_factory() as db:
        initialize_policy(db, version=0, confirmed=True, actor_user_id=None)
        db.commit()
    barrier = Barrier(2)

    def save(name):
        with postgres_session_factory() as db:
            barrier.wait(timeout=10)
            try:
                update_policy(db, section="beta", changes={"beta.round_name": name},
                    version=1, confirmed=False, actor_user_id=None)
                db.commit()
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(save, ["Rodada A", "Rodada B"])) == [200, 409]
    with postgres_session_factory() as db:
        row, policy = read_policy(db)
        assert row.configuration_version == 2
        assert policy.round_name in {"Rodada A", "Rodada B"}
        assert db.query(AuditEvent).filter_by(event="admin.settings_changed").count() == 1


def test_budget_reduction_below_held_use_is_durable_and_invalid_patch_rolls_back(postgres_session_factory):
    with postgres_session_factory() as db:
        db.add(PlatformProviderBudget(provider="assemblyai", limit_cents=1500, reserved_cents=800,
            alert_cents=1200, round_id="synthetic-round"))
        db.flush()
        initialize_policy(db, version=0, confirmed=True, actor_user_id=None)
        db.commit()
        update_policy(db, section="assemblyai", changes={"assemblyai.hard_stop_usd": Decimal(6),
            "assemblyai.alert_usd": Decimal(5)}, version=1, confirmed=True, actor_user_id=None)
        db.commit()
    with postgres_session_factory() as db:
        row, _ = read_policy(db)
        assert row.limit_cents == 600 and row.reserved_cents == 800
        with pytest.raises(HTTPException) as denied:
            update_policy(db, section="assemblyai", changes={"assemblyai.alert_usd": Decimal(7)},
                version=2, confirmed=True, actor_user_id=None)
        assert denied.value.status_code == 422
        db.rollback()
        row, _ = read_policy(db)
        assert row.alert_cents == 500 and row.configuration_version == 2
        assert db.query(AuditEvent).filter_by(event="admin.settings_changed").count() == 1


def test_migration_reverses_only_without_configuration_or_committed_history(postgres_engine, postgres_session_factory, monkeypatch):
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    migration = ScriptDirectory.from_config(config).get_revision("20261015_0018").module
    with postgres_engine.begin() as connection:
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.downgrade()
        assert "operational_policy" not in {c["name"] for c in inspect(connection).get_columns("platform_provider_budgets")}
        migration.upgrade()
        assert "operational_policy" in {c["name"] for c in inspect(connection).get_columns("platform_provider_budgets")}
    with postgres_session_factory() as db:
        initialize_policy(db, version=0, confirmed=True, actor_user_id=None)
        db.commit()
    with postgres_engine.begin() as connection:
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError, match="Preserve operational policy"):
            migration.downgrade()
