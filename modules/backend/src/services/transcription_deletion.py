"""One deletion rule for the transcription and its 1:1 meeting."""

import logging
from fastapi import HTTPException

from sqlalchemy.orm import Session

from ..models import Transcription, TranscriptionJob, User
from sqlalchemy.exc import OperationalError
from .audit import append_audit_event
from .audio_storage import input_reference, schedule_audio_cleanup, cleanup_after_commit

logger = logging.getLogger(__name__)


class ActiveTranscriptionError(ValueError):
    pass


def delete_transcription_data(
    db: Session, transcription: Transcription, actor_user_id: int | None
) -> dict[str, bool]:
    """Cascade meeting/job/ownership in one DB commit, then clean the input."""
    if actor_user_id is not None:
        try:
            owner = db.query(User).filter_by(id=actor_user_id).with_for_update(key_share=True, nowait=True).populate_existing().one_or_none()
            if owner is None or not owner.is_active:
                raise HTTPException(401, "Entre novamente na sua conta.")
        except OperationalError as error:
            db.rollback()
            if getattr(error.orig, "sqlstate", None) == "55P03":
                raise ActiveTranscriptionError("Account operation is active") from None
            raise HTTPException(503, "Não foi possível excluir agora. Tente novamente.") from None
    from .account_deletion import ensure_no_legacy_minutes_jobs
    ensure_no_legacy_minutes_jobs([transcription.id])
    job = (
        db.query(TranscriptionJob)
        .filter(TranscriptionJob.transcription_id == transcription.id)
        .first()
    )
    if transcription.status in {"queued", "processing"} or (
        job and job.status in {"queued", "processing"}
    ):
        raise ActiveTranscriptionError("Active transcription jobs cannot be deleted")

    reference = input_reference(job) if job else None
    try:
        if transcription.meeting is not None:
            append_audit_event(
                db,
                event="meeting.deleted",
                actor_user_id=actor_user_id,
                resource_type="meeting",
                resource_id=transcription.id,
            )
        append_audit_event(
            db,
            event="transcription.deleted",
            actor_user_id=actor_user_id,
            resource_type="transcription",
            resource_id=transcription.id,
        )
        schedule_audio_cleanup(db, reference)
        db.delete(transcription)
        db.commit()
    except Exception:
        db.rollback()
        raise

    cleanup = cleanup_after_commit(db, [reference])
    cleanup_pending = bool(cleanup["pending"] or cleanup["failed"])
    if cleanup_pending:
        logger.warning("Input cleanup incomplete for transcription %s", transcription.id)
    return {"cleanup_pending": cleanup_pending}
