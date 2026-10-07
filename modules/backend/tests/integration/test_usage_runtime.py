"""PostgreSQL idempotency, ownership, journal replay and migration coverage."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from src.models import UsageEvent, UsagePrice, User
from src.services.usage_metering import reconcile_usage, record_event, spool_directory


pytestmark = pytest.mark.postgres
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _seed_user(factory):
    db = factory()
    try:
        user = User(username="usage-runtime", email=f"usage-{uuid4().hex}@example.invalid", hashed_password="fixture")
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def _usage_kwargs(operation_id, user_id=None):
    return dict(
        operation_id=operation_id, resource_type="transcription", resource_id="42",
        operation="transcription", provider="assemblyai", credential_source="platform",
        metric="provider_audio_seconds", unit="second", quantity=12.5, status="completed",
        phase="provider_response", user_id=user_id, model="universal-2",
        measurement_source="provider_response",
    )


def test_concurrent_same_usage_event_is_inserted_once(postgres_session_factory):
    operation_id = str(uuid4())
    barrier = Barrier(2)

    def record():
        barrier.wait(timeout=10)
        return record_event(**_usage_kwargs(operation_id), session_factory=postgres_session_factory)

    with ThreadPoolExecutor(max_workers=2) as executor:
        event_ids = list(executor.map(lambda _index: record(), range(2)))

    assert event_ids[0] == event_ids[1]
    db = postgres_session_factory()
    try:
        assert db.query(UsageEvent).filter_by(operation_id=operation_id).count() == 1
    finally:
        db.close()


def test_journal_dry_run_replay_freezes_estimate_and_owner_delete_anonymizes(postgres_session_factory):
    user_id = _seed_user(postgres_session_factory)
    occurred_at = datetime.now(timezone.utc)
    db = postgres_session_factory()
    try:
        price = UsagePrice(
            id=str(uuid4()), catalog_version="runtime-v1", provider="assemblyai",
            model="universal-2", metric="provider_audio_seconds", unit="second",
            currency="USD", unit_price=Decimal("0.12"), unit_quantity=Decimal("3600"),
            effective_from=occurred_at - timedelta(days=1), source="fixture",
        )
        db.add(price)
        db.commit()
        price_id = price.id
    finally:
        db.close()

    operation_id = str(uuid4())
    journal_event_id = record_event(
        **{**_usage_kwargs(operation_id, user_id), "credential_source": "user",
           "quantity": 60, "occurred_at": occurred_at},
        session_factory=postgres_session_factory, journal_only=True,
    )
    assert journal_event_id
    journal_file = spool_directory() / f"{journal_event_id}.json"
    assert journal_file.exists()

    dry_run = reconcile_usage(apply=False, session_factory=postgres_session_factory)
    assert dry_run == {"pending": 1, "delivered": 0, "failed": 0}
    assert journal_file.exists()
    db = postgres_session_factory()
    try:
        assert db.get(UsageEvent, journal_event_id) is None
        db.add(UsagePrice(
            id=str(uuid4()), catalog_version="runtime-v2", provider="assemblyai",
            model="universal-2", metric="provider_audio_seconds", unit="second",
            currency="USD", unit_price=Decimal("9.99"), unit_quantity=Decimal("3600"),
            effective_from=occurred_at + timedelta(days=1), source="fixture",
        ))
        db.commit()
    finally:
        db.close()

    applied = reconcile_usage(apply=True, session_factory=postgres_session_factory)
    assert applied == {"pending": 1, "delivered": 1, "failed": 0}
    assert not journal_file.exists()

    db = postgres_session_factory()
    try:
        event = db.get(UsageEvent, journal_event_id)
        frozen_estimate = event.estimated_cost
        assert event.price_id == price_id
        assert frozen_estimate == Decimal("0.002000000000")
        assert event.user_id == user_id
        db.delete(db.get(User, user_id))
        db.commit()
        db.expire_all()
        event = db.get(UsageEvent, journal_event_id)
        assert event.user_id is None
        assert event.quantity == Decimal("60.000000000")
        assert event.estimated_cost == frozen_estimate
        assert event.cost_reason == "configured_estimate_not_invoice"
    finally:
        db.close()


def test_usage_migration_additive_and_downgrade_guard_in_isolated_schema(postgres_engine, monkeypatch):
    schema = "usage_migration_" + uuid4().hex
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision("20261007_0012").module

    try:
        with postgres_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}"'))
            connection.execute(text("CREATE TABLE users (id integer PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE transcription_jobs (id integer PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE meeting_intelligence (id integer PRIMARY KEY)"))
            monkeypatch.setattr(revision, "op", Operations(MigrationContext.configure(connection)))

            revision.upgrade()
            inspector = inspect(connection)
            assert {"usage_prices", "usage_events"}.issubset(inspector.get_table_names())
            assert "usage_attempt_id" in {column["name"] for column in inspector.get_columns("transcription_jobs")}
            assert "usage_attempt_id" in {column["name"] for column in inspector.get_columns("meeting_intelligence")}

            connection.execute(text(
                "INSERT INTO usage_prices (id,catalog_version,provider,model,metric,unit,currency,unit_price,unit_quantity,effective_from,source) "
                "VALUES (:id,'test','assemblyai','universal-2','provider_audio_seconds','second','USD',0,1,:now,'fixture')"
            ), {"id": str(uuid4()), "now": datetime.now(timezone.utc)})
            with pytest.raises(RuntimeError, match="Export and preserve usage history"):
                revision.downgrade()
            assert "usage_events" in inspect(connection).get_table_names()
            assert "usage_attempt_id" in {column["name"] for column in inspect(connection).get_columns("transcription_jobs")}

            connection.execute(text("DELETE FROM usage_prices"))
            revision.downgrade()
            inspector = inspect(connection)
            assert "usage_prices" not in inspector.get_table_names()
            assert "usage_events" not in inspector.get_table_names()
            assert "usage_attempt_id" not in {column["name"] for column in inspector.get_columns("transcription_jobs")}
            assert "usage_attempt_id" not in {column["name"] for column in inspector.get_columns("meeting_intelligence")}
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
