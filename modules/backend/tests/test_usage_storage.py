from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.models import UsageEvent
from src.services.usage_storage import deletion_context, record_object_delete, record_object_put
from src.services.usage_metering import reconcile_usage


def test_storage_exact_bytes_and_observed_lifetime_survive_resource_deletion(db_context):
    db = db_context["session_factory"]()
    reference = "object:opaque-synthetic-key"
    record_object_put(db, reference, 12345, resource_id=7, user_id=1)
    context = deletion_context(db, reference)
    assert context["quantity"] == Decimal(12345)
    assert context["user_id"] == 1
    assert record_object_delete(db, context, context["occurred_at"] + timedelta(seconds=10))
    db.commit()
    reconcile_usage(apply=True, session_factory=db_context["session_factory"])
    assert record_object_delete(db, context, context["occurred_at"] + timedelta(seconds=20))
    db.commit()
    reconcile_usage(apply=True, session_factory=db_context["session_factory"])
    rows = db.query(UsageEvent).all()
    assert len(rows) == 3
    assert {r.metric: r.quantity for r in rows} == {
        "stored_bytes": Decimal(12345), "deleted_bytes": Decimal(12345), "byte_seconds": Decimal(123450)}
    assert all(r.estimated_cost is None for r in rows)
    assert all(reference not in r.operation_id for r in rows)
    db.close()


def test_unmetered_legacy_object_is_explicitly_unknown_not_zero(db_context):
    db = db_context["session_factory"]()
    context = deletion_context(db, "legacy-local-file")
    assert record_object_delete(db, context, datetime.now(timezone.utc))
    db.commit()
    reconcile_usage(apply=True, session_factory=db_context["session_factory"])
    rows = db.query(UsageEvent).all()
    assert len(rows) == 2 and all(r.quantity is None for r in rows)
    assert all(r.user_id is None for r in rows)
    db.close()


def test_storage_clock_reversal_is_unknown_not_zero(db_context):
    db = db_context["session_factory"]()
    record_object_put(db, "object:clock-fixture", 10, resource_id=7, user_id=1)
    context = deletion_context(db, "object:clock-fixture")
    assert record_object_delete(db, context, context["occurred_at"] - timedelta(seconds=1))
    db.commit()
    reconcile_usage(apply=True, session_factory=db_context["session_factory"])
    assert db.query(UsageEvent).filter_by(metric="byte_seconds").one().quantity is None
    db.close()


def test_usage_journal_configuration_cannot_overlap_upload_cleanup(db_context, monkeypatch):
    from src.config import settings
    monkeypatch.setattr(settings, "USAGE_SPOOL_DIRECTORY", settings.AUDIO_UPLOAD_DIRECTORY + "/journal")
    assert "USAGE_SPOOL_DIRECTORY must be a dedicated private directory outside audio uploads" in settings.validate_startup()
