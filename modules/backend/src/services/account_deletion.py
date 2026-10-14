"""API-only identity cleanup; retries never restore an erased domain account."""
import logging
import os
from datetime import datetime, timezone

from ..config import settings
from ..models import AccountDeletion
from ..workers.config import get_transcription_queue
from .transcription_deletion import ActiveTranscriptionError

logger = logging.getLogger(__name__)


def ensure_no_legacy_minutes_jobs(transcription_ids):
    """Compatibility jobs lack a DB revision; inspect live RQ under owner lock.

    Publication holds that lock too, including the HTTP wait. This check also
    covers a timed-out HTTP request whose provider call is still running.
    """
    if not transcription_ids:
        return
    from fastapi import HTTPException
    prefixes = tuple(f"meeting_minutes_{item}_" for item in transcription_ids)
    try:
        queue = get_transcription_queue()
        ids = queue.get_job_ids() + queue.started_job_registry.get_job_ids()
    except Exception:
        raise HTTPException(503, "Não foi possível verificar os processamentos. Tente novamente.") from None
    if any(job_id.startswith(prefixes) for job_id in ids):
        raise ActiveTranscriptionError("Active legacy analysis prevents erasure")


def delete_firebase_identity(project_id: str, uid: str) -> None:
    # Use only this app's configured project; never modify IAM or other projects.
    if (not settings.FIREBASE_AUTH_ENABLED or project_id != settings.FIREBASE_PROJECT_ID
            or os.getenv("FIREBASE_AUTH_EMULATOR_HOST")):
        raise RuntimeError("Identity cleanup configuration unavailable")
    import firebase_admin
    from firebase_admin import auth
    from .firebase_identity import _app_lock
    with _app_lock:
        name = "usagi-auth-" + project_id
        try:
            app = firebase_admin.get_app(name)
        except ValueError:
            app = firebase_admin.initialize_app(options={
                "projectId": project_id,
                "httpTimeout": settings.FIREBASE_HTTP_TIMEOUT_SECONDS,
            }, name=name)
    if app.project_id != project_id:
        raise RuntimeError("Identity cleanup project mismatch")
    try:
        auth.delete_user(uid, app=app)
    except auth.UserNotFoundError:
        pass  # A lost acknowledgement is safe to retry.


def retry_identity_cleanup(db, *, deletion_id=None, apply=False, limit=100) -> dict:
    """Dry-run by default. Run in API context with ADC, never in the ML Worker."""
    query = db.query(AccountDeletion).filter(AccountDeletion.firebase_uid.is_not(None))
    if deletion_id is not None:
        query = query.filter_by(id=deletion_id)
    rows = query.order_by(AccountDeletion.requested_at).with_for_update(skip_locked=True).limit(limit).all()
    result = {"candidates": len(rows), "completed": 0, "pending": 0, "dry_run": not apply}
    for row in rows:
        if not apply:
            result["pending"] += 1
            continue
        row.attempts += 1
        row.last_attempt_at = datetime.now(timezone.utc)
        try:
            delete_firebase_identity(row.firebase_project_id, row.firebase_uid)
        except Exception as error:
            # Third-party errors may contain credentials/PII: log receipt ID + type only.
            logger.warning("Identity cleanup pending receipt=%s error=%s", row.id, type(error).__name__)
            result["pending"] += 1
        else:
            row.firebase_uid = None
            row.firebase_project_id = None
            row.completed_at = datetime.now(timezone.utc)
            result["completed"] += 1
    if apply:
        db.commit()
    else:
        db.rollback()
    return result
