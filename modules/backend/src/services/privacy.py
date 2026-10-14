"""Internal, testable data export and erasure capabilities."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import AuditEvent, MeetingActionSuggestionReview, Transcription, TranscriptionOwnership, User, UsageEvent
from ..authorization import ownership_filter
from .audit import append_audit_event
from .audio_storage import input_reference, schedule_audio_cleanup, cleanup_after_commit
from .transcription_deletion import ActiveTranscriptionError
from .provider_credentials import preferences_for


@dataclass(frozen=True)
class ErasureResult:
    user_id: int
    transcriptions_deleted: int
    files_considered: int
    files_cleaned: int


def _owned_transcriptions_query(db: Session, user: User):
    return (
        db.query(Transcription)
        .join(TranscriptionOwnership)
        .filter(
            ownership_filter(user.id, user.username, user.registration_source)
        )
    )


def export_user_data(db: Session, user: User) -> dict:
    """Export identity and owned product data, never hashes, secrets, or file paths."""
    transcriptions = _owned_transcriptions_query(db, user).order_by(Transcription.id).all()
    audit_rows = (
        db.query(AuditEvent)
        .filter(AuditEvent.actor_user_id == user.id)
        .order_by(AuditEvent.id)
        .all()
    )
    payload = {
        "format": "usagi-user-export-v1",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "active": user.is_active,
            "plan": user.plan,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        },
        "transcriptions": [],
        "preferences": preferences_for(db, user.id),
        "usage": [
            {
                "id": row.id, "resource_type": row.resource_type,
                "resource_id": row.resource_id, "operation": row.operation,
                "provider": row.provider, "credential_source": row.credential_source,
                "metric": row.metric, "unit": row.unit,
                "quantity": str(row.quantity) if row.quantity is not None else None,
                "status": row.status, "model": row.model,
                "occurred_at": row.occurred_at.isoformat(),
            }
            for row in db.query(UsageEvent).filter_by(user_id=user.id)
            .order_by(UsageEvent.occurred_at, UsageEvent.id).all()
        ],
        "audit_events": [
            {
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "event": row.event,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
            }
            for row in audit_rows
        ],
    }
    for transcription in transcriptions:
        item = transcription.to_dict()
        # Storage identifiers and internal diagnostics are not portable user data.
        item.pop("filename", None)
        item.pop("error_message", None)
        item["meeting"] = (
            {
                "title": transcription.meeting.title,
                "language": transcription.meeting.language,
                "created_at": transcription.meeting.created_at.isoformat()
                if transcription.meeting.created_at else None,
                "speakers": [
                    {"id": speaker.speaker_id, "display_name": speaker.display_name}
                    for speaker in transcription.meeting.speakers
                ],
                "intelligence_revisions": [
                    {"revision": row.revision, "status": row.status, "schema_version": row.schema_version,
                     "provider": row.provider, "model": row.model, "result": row.result}
                    for row in sorted(transcription.meeting.intelligence_revisions, key=lambda item: item.revision)
                ],
                "action_items": [
                    action.to_dict()
                    for action in sorted(transcription.meeting.action_items, key=lambda item: item.id)
                ],
                "action_suggestion_reviews": [
                    {"source_revision": review.source_revision, "source_index": review.source_index,
                     "status": review.status}
                    for review in db.query(MeetingActionSuggestionReview)
                    .filter_by(meeting_id=transcription.meeting.id)
                    .order_by(MeetingActionSuggestionReview.source_revision,
                              MeetingActionSuggestionReview.source_index).all()
                ],
            }
            if transcription.meeting else None
        )
        item["job"] = (
            {
                "status": transcription.job.status,
                "transcription_model": transcription.job.transcription_model,
                "use_diarization": transcription.job.use_diarization,
                "created_at": transcription.job.created_at.isoformat()
                if transcription.job.created_at
                else None,
                "started_at": transcription.job.started_at.isoformat()
                if transcription.job.started_at
                else None,
                "completed_at": transcription.job.completed_at.isoformat()
                if transcription.job.completed_at
                else None,
                "failed_at": transcription.job.failed_at.isoformat()
                if transcription.job.failed_at
                else None,
            }
            if transcription.job
            else None
        )
        payload["transcriptions"].append(item)

    append_audit_event(
        db,
        event="user.data_exported",
        actor_user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        metadata={"transcription_count": len(transcriptions)},
    )
    db.commit()
    return payload


def erase_user_data(db: Session, user: User) -> ErasureResult:
    """Delete DB data transactionally, then attempt idempotent file cleanup."""
    user_id = user.id
    transcriptions = _owned_transcriptions_query(db, user).all()
    if any(row.status in {"queued", "processing"} or
           (row.job and row.job.status in {"queued", "processing"}) for row in transcriptions):
        raise ActiveTranscriptionError("Active transcription jobs prevent user erasure")
    paths = [input_reference(row.job) for row in transcriptions if row.job]

    append_audit_event(
        db,
        event="user.data_deleted",
        actor_user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        metadata={"transcription_count": len(transcriptions)},
    )
    for transcription in transcriptions:
        if transcription.job:
            schedule_audio_cleanup(db, input_reference(transcription.job))
        db.delete(transcription)
    db.delete(user)
    db.commit()

    files_cleaned = cleanup_after_commit(db, paths)["deleted"]
    return ErasureResult(
        user_id=user_id,
        transcriptions_deleted=len(transcriptions),
        files_considered=len(paths),
        files_cleaned=files_cleaned,
    )
