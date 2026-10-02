"""One deletion rule for the transcription and its 1:1 meeting."""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import Transcription, TranscriptionJob
from .audit import append_audit_event
from .storage_lifecycle import delete_file_idempotently

logger = logging.getLogger(__name__)


class ActiveTranscriptionError(ValueError):
    pass


def delete_transcription_data(
    db: Session, transcription: Transcription, actor_user_id: int | None
) -> None:
    """Cascade meeting/job/ownership in one DB commit, then clean the input."""
    job = (
        db.query(TranscriptionJob)
        .filter(TranscriptionJob.transcription_id == transcription.id)
        .first()
    )
    if transcription.status in {"queued", "processing"} or (
        job and job.status in {"queued", "processing"}
    ):
        raise ActiveTranscriptionError("Active transcription jobs cannot be deleted")

    input_path = Path(job.input_path) if job else None
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
        db.delete(transcription)
        db.commit()
    except Exception:
        db.rollback()
        raise

    if input_path and not delete_file_idempotently(input_path) and input_path.exists():
        logger.warning("Input cleanup incomplete for transcription %s", transcription.id)
