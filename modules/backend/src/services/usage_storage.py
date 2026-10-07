"""Exact stored bytes and observed lifetime; no object keys or paths in ledger."""
import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import sessionmaker

from ..models import UsageEvent
from .usage_metering import event_id, record_event, spool_directory, _read_journal, utc

logger = logging.getLogger(__name__)


def object_operation(reference):
    return "object:" + hashlib.sha256(reference.encode("utf-8")).hexdigest()


def record_object_put(db, reference, size_bytes, *, resource_id, user_id=None, guest_session_id=None):
    return record_event(operation_id=object_operation(reference), resource_type="object",
        resource_id=str(resource_id), operation="storage", provider="object_storage",
        credential_source="none", metric="stored_bytes", unit="byte", quantity=size_bytes,
        phase="put", user_id=user_id, guest_session_id=guest_session_id,
        measurement_source="validated_upload", model="local", session_factory=sessionmaker(bind=db.get_bind()))


def deletion_context(db, reference):
    """Find original attribution even after resource deletion or metric outage."""
    operation_id = object_operation(reference)
    identifier = event_id(operation_id, "stored_bytes", "put")
    try:
        row = db.get(UsageEvent, identifier)
        if row:
            return dict(operation_id=operation_id, resource_id=row.resource_id, user_id=row.user_id,
                        guest_session_id=row.guest_session_id, quantity=row.quantity, occurred_at=utc(row.occurred_at))
        path = spool_directory() / (identifier + ".json")
        if path.exists():
            pending = _read_journal(path)
            return dict(operation_id=operation_id, resource_id=pending["resource_id"], user_id=pending["user_id"],
                        guest_session_id=pending["guest_session_id"], quantity=pending["quantity"],
                        occurred_at=datetime.fromisoformat(pending["occurred_at"]))
    except Exception as exc:
        logger.warning("Storage usage attribution unavailable (%s)", type(exc).__name__)
    return dict(operation_id=operation_id, resource_id="unattributed", user_id=None,
                guest_session_id=None, quantity=None, occurred_at=None)


def record_object_delete(db, context, deleted_at):
    values = dict(operation_id=context["operation_id"], resource_type="object", resource_id=context["resource_id"],
                  operation="storage", provider="object_storage", credential_source="none", model="local",
                  user_id=context["user_id"], guest_session_id=context["guest_session_id"],
                  pricing_session=db, journal_only=True, occurred_at=deleted_at)
    deleted_id = record_event(**values, metric="deleted_bytes", unit="byte", quantity=context["quantity"],
                             phase="delete", measurement_source="cleanup_observed")
    lifetime = None
    if context["quantity"] is not None and context["occurred_at"] is not None:
        elapsed = max(Decimal(0), Decimal(str((deleted_at - context["occurred_at"]).total_seconds())))
        lifetime = Decimal(str(context["quantity"])) * elapsed
    lifetime_id = record_event(**values, metric="byte_seconds", unit="byte_second", quantity=lifetime,
                              phase="delete", measurement_source="observed_storage_lifetime")
    return deleted_id is not None and lifetime_id is not None
