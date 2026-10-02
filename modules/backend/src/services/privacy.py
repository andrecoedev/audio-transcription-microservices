"""Internal, testable data export and erasure capabilities."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import AuditEvent, MeetingActionSuggestionReview, Transcription, TranscriptionOwnership, User
from ..authorization import ownership_filter
from .audit import append_audit_event
from .storage_lifecycle import delete_file_idempotently


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
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        },
        "transcriptions": [],
        "audit_events": [
            {
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "event": row.event,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "metadata": row.event_metadata,
            }
            for row in audit_rows
        ],
    }
    for transcription in transcriptions:
        item = transcription.to_dict()
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
                     "provider": row.provider, "model": row.model, "result": row.result,
                     "source_metadata": row.source_metadata}
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
    paths = [row.job.input_path for row in transcriptions if row.job and row.job.input_path]

    append_audit_event(
        db,
        event="user.data_deleted",
        actor_user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        metadata={"transcription_count": len(transcriptions)},
    )
    for transcription in transcriptions:
        db.delete(transcription)
    db.delete(user)
    db.commit()

    files_cleaned = sum(delete_file_idempotently(path) for path in paths)
    return ErasureResult(
        user_id=user_id,
        transcriptions_deleted=len(transcriptions),
        files_considered=len(paths),
        files_cleaned=files_cleaned,
    )
