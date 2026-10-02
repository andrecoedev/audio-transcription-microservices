"""Small write-only audit service.

There is intentionally no audit CRUD router. Application code may append
events through this function; retention/deletion is an operational task.
"""

from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditEvent


ALLOWED_EVENTS = {
    "user.login",
    "transcription.created",
    "transcription.completed",
    "transcription.failed",
    "transcription.deleted",
    "meeting.created",
    "meeting.title_updated",
    "meeting.speaker_renamed",
    "meeting.deleted",
    "meeting_action.created",
    "meeting_action.updated",
    "meeting_action.deleted",
    "intelligence.requested",
    "intelligence.completed",
    "intelligence.failed",
    "user.data_exported",
    "user.data_deleted",
}


def append_audit_event(
    db: Session,
    *,
    event: str,
    actor_user_id: int | None = None,
    actor_type: str = "user",
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append a content-free event to the caller's current transaction."""
    if event not in ALLOWED_EVENTS:
        raise ValueError(f"Unsupported audit event: {event}")
    row = AuditEvent(
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        event=event,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        event_metadata=metadata or {},
    )
    db.add(row)
    return row
