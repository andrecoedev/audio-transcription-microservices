"""Dry-run-first guest cleanup, serialized with conversion and upload."""
from datetime import datetime, timezone

from ..models import GuestSession, Transcription, TranscriptionOwnership
from .audit import append_audit_event
from .audio_storage import input_reference, schedule_audio_cleanup, cleanup_after_commit


def apply_guest_retention(db, *, apply=False, now=None):
    expired = db.query(GuestSession).filter(GuestSession.expires_at <= (now or datetime.now(timezone.utc)))
    if apply:
        expired = expired.with_for_update()
    sessions = expired.all()
    result = {"sessions_deleted": 0, "transcriptions_deleted": 0, "candidates": 0,
              "active_preserved": 0, "files_failed": 0, "dry_run": not apply}
    paths = []
    for session in sessions:
        rows = db.query(Transcription).join(TranscriptionOwnership).filter(
            TranscriptionOwnership.guest_session_id == session.id,
            TranscriptionOwnership.user_id.is_(None),
        ).all()
        active = False
        for row in rows:
            if row.status in {"queued", "processing"} or (
                row.job and row.job.status in {"queued", "processing"}
            ):
                result["active_preserved"] += 1
                active = True
                continue
            result["candidates"] += 1
            if apply:
                if row.job:
                    reference = input_reference(row.job)
                    paths.append(reference)
                    schedule_audio_cleanup(db, reference)
                append_audit_event(db, event="transcription.deleted", actor_type="system",
                    resource_type="transcription", resource_id=row.id, metadata={"reason": "guest_retention"})
                db.delete(row)
                result["transcriptions_deleted"] += 1
        if apply and not active:
            db.flush()  # Remove RESTRICTed ownership before its session.
            db.delete(session)
            result["sessions_deleted"] += 1
    if apply:
        db.commit()
        result["files_failed"] = cleanup_after_commit(db, paths)["failed"]
    return result
