"""Jobs RQ de transcrição executados fora do processo FastAPI."""

import logging
import time
from datetime import datetime, timezone

from rq.exceptions import NoSuchJobError
from rq.job import Job

from ..config import settings
from ..database import SessionLocal
from ..models import Meeting, MeetingSpeaker, Transcription, TranscriptionJob, TranscriptionOwnership
from ..services.processing_engines import initialize_processing_engines
from ..services.audit import append_audit_event
from ..services.meeting_projection import ordered_segments, speaker_ids
from ..services.storage_lifecycle import delete_file_idempotently
from ..services.transcription_processing_service import (
    TranscriptionProcessingService,
    PublicAudioDurationError,
    TranscriptionProcessingError,
)

logger = logging.getLogger(__name__)
_processing_service: TranscriptionProcessingService | None = None


def initialize_worker_engines(
    factories=None,
) -> dict[str, bool]:
    """Initialize engines inside a forked RQ work horse, never its parent."""
    global _processing_service

    validation_errors = settings.validate_startup(require_api_security=False)
    if validation_errors:
        raise RuntimeError("Invalid worker configuration: " + "; ".join(validation_errors))

    if factories is None:
        from ..utils.gpu_utils import log_device_info, optimize_gpu_settings

        log_device_info()
        optimize_gpu_settings()

    status = initialize_processing_engines(
        hf_token=settings.HF_TOKEN,
        aai_api_key=settings.AAI_API_KEY,
        gemini_api_key=settings.GEMINI_API_KEY,
        factories=factories,
    )
    if _processing_service is None:
        _processing_service = TranscriptionProcessingService()
    logger.info("Worker processing engines initialized: %s", status)
    return status


def get_processing_service() -> TranscriptionProcessingService:
    global _processing_service
    if _processing_service is None:
        initialize_worker_engines()
    assert _processing_service is not None
    return _processing_service


def recover_pending_jobs(queue) -> int:
    """Reconcilia jobs persistidos com o RQ sem duplicar jobs ainda ativos."""
    db = SessionLocal()
    recovered = 0
    try:
        queue.started_job_registry.cleanup()
        pending_jobs = (
            db.query(TranscriptionJob)
            .filter(TranscriptionJob.status.in_(["queued", "processing"]))
            .all()
        )
        for db_job in pending_jobs:
            rq_job_id = f"transcription_{db_job.transcription_id}"
            existing = None
            try:
                existing = Job.fetch(rq_job_id, connection=queue.connection)
            except NoSuchJobError:
                pass

            if existing is not None:
                rq_status = existing.get_status(refresh=True)
                rq_status = getattr(rq_status, "value", rq_status)
                if rq_status in {"queued", "started", "deferred", "scheduled"}:
                    continue
                existing.delete()

            transcription = db.get(Transcription, db_job.transcription_id)
            if not transcription:
                logger.warning(
                    "Pending job %s has no transcription record",
                    db_job.transcription_id,
                )
                continue

            db_job.status = "queued"
            db_job.error_message = None
            db_job.started_at = None
            db_job.completed_at = None
            db_job.failed_at = None
            transcription.status = "queued"
            transcription.error_message = None
            # Make the durable state visible before publishing the RQ message.
            db.commit()
            queue.enqueue(
                process_transcription_job_sync,
                db_job.transcription_id,
                job_id=rq_job_id,
                **({"job_timeout": db_job.timeout_seconds} if db_job.timeout_seconds else {}),
            )
            recovered += 1

        db.commit()
        if recovered:
            logger.info("Recovered %s pending transcription jobs", recovered)
        return recovered
    except Exception:
        db.rollback()
        logger.exception("Unable to recover pending transcription jobs")
        raise
    finally:
        db.close()


def _claim_transcription_job(transcription_id: int) -> dict | None:
    """Atomically claim a queued job in a short database transaction."""
    db = SessionLocal()
    try:
        job = (
            db.query(TranscriptionJob)
            .filter(TranscriptionJob.transcription_id == transcription_id)
            .first()
        )
        transcription = db.get(Transcription, transcription_id)
        if not job or not transcription:
            logger.warning("Job or transcription not found for id=%s", transcription_id)
            return None

        if job.status in {"completed", "done"}:
            logger.info("Transcription job %s was already completed", transcription_id)
            return {"claim_status": "already_done"}

        now = datetime.now(timezone.utc)
        claimed = (
            db.query(TranscriptionJob)
            .filter(
                TranscriptionJob.transcription_id == transcription_id,
                TranscriptionJob.status == "queued",
            )
            .update(
                {
                    TranscriptionJob.status: "processing",
                    TranscriptionJob.error_message: None,
                    TranscriptionJob.started_at: now,
                    TranscriptionJob.completed_at: None,
                    TranscriptionJob.failed_at: None,
                },
                synchronize_session="fetch",
            )
        )
        if claimed != 1:
            db.rollback()
            logger.info("Transcription job %s is already being processed", transcription_id)
            return {"claim_status": "already_processing"}

        db.query(Transcription).filter(Transcription.id == transcription_id).update(
            {
                Transcription.status: "processing",
                Transcription.error_message: None,
            },
            synchronize_session="fetch",
        )
        db.commit()
        return {
            "claim_status": "claimed",
            "input_path": job.input_path,
            "use_diarization": job.use_diarization,
            "transcription_model": job.transcription_model,
            "max_duration_seconds": job.max_duration_seconds,
            "guest_context": db.query(TranscriptionOwnership.id).filter(
                TranscriptionOwnership.transcription_id == transcription_id,
                TranscriptionOwnership.guest_session_id.isnot(None),
            ).first() is not None,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _persist_completed_job(transcription_id: int, result, processing_time: float) -> None:
    """Persist transcript, meeting and both completed statuses in one commit."""
    db = SessionLocal()
    try:
        job = (
            db.query(TranscriptionJob)
            .filter(TranscriptionJob.transcription_id == transcription_id)
            .one()
        )
        transcription = db.get(Transcription, transcription_id)
        transcription.duration_seconds = result.duration_seconds
        transcription.transcription_model = job.transcription_model
        transcription.use_diarization = job.use_diarization
        transcription.segments = ordered_segments(result.segments)
        transcription.num_speakers = result.num_speakers
        transcription.word_count = result.word_count
        transcription.processing_time_seconds = processing_time
        transcription.status = "completed"
        transcription.error_message = None
        meeting = db.get(Meeting, transcription_id)
        if meeting is None:
            language = result.engine_metadata.get("language") if result.engine_metadata else None
            if not isinstance(language, str) or language == "auto" or len(language) > 16:
                language = None
            meeting = Meeting(
                id=transcription_id,
                title=transcription.original_filename,
                language=language,
            )
            db.add(meeting)
            db.flush()
        known_speakers = {speaker.speaker_id for speaker in meeting.speakers}
        for speaker_id in speaker_ids(transcription.segments):
            if speaker_id not in known_speakers:
                meeting.speakers.append(MeetingSpeaker(speaker_id=speaker_id))
        job.status = "completed"
        job.error_message = None
        job.completed_at = datetime.now(timezone.utc)
        job.failed_at = None
        append_audit_event(
            db,
            event="transcription.completed",
            actor_type="system",
            resource_type="transcription",
            resource_id=transcription_id,
            metadata={"provider": job.transcription_model},
        )
        append_audit_event(
            db,
            event="meeting.created",
            actor_type="system",
            resource_type="meeting",
            resource_id=transcription_id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _persist_failed_job(transcription_id: int, public_error: str) -> None:
    """Persist a safe public failure message in one short transaction."""
    db = SessionLocal()
    try:
        transcription = db.get(Transcription, transcription_id)
        job = (
            db.query(TranscriptionJob)
            .filter(TranscriptionJob.transcription_id == transcription_id)
            .first()
        )
        if transcription:
            transcription.status = "failed"
            transcription.error_message = public_error
        if job:
            job.status = "failed"
            job.error_message = public_error
            job.failed_at = datetime.now(timezone.utc)
            job.completed_at = None
        append_audit_event(
            db,
            event="transcription.failed",
            actor_type="system",
            resource_type="transcription",
            resource_id=transcription_id,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(
            "Unable to persist failure for transcription %s (%s)",
            transcription_id,
            type(exc).__name__,
        )
        raise
    finally:
        db.close()


def process_transcription_job_sync(transcription_id: int) -> dict:
    """Run ML without an open DB transaction, then persist the result atomically."""
    input_path: str | None = None
    claimed = False

    try:
        claim = _claim_transcription_job(transcription_id)
        if claim is None:
            return {"status": "failed", "error": "Transcription job not found"}
        if claim["claim_status"] == "already_done":
            return {"status": "already_done"}
        if claim["claim_status"] == "already_processing":
            return {"status": "already_processing"}

        claimed = True
        input_path = claim["input_path"]
        if claim["guest_context"]:
            # Also protect previously queued/recovered Guest jobs. P4-04 must
            # validate provider admission and budget before any engine loading.
            raise TranscriptionProcessingError("Visitor AssemblyAI processing is not validated")
        logger.info("Transcription job %s started", transcription_id)
        started_at = time.monotonic()

        result = get_processing_service().process_transcription(
            file_path=input_path,
            use_diarization=claim["use_diarization"],
            transcription_model=claim["transcription_model"],
            **({"max_duration_seconds": claim["max_duration_seconds"]} if claim["max_duration_seconds"] else {}),
        )
        processing_time = time.monotonic() - started_at
        _persist_completed_job(transcription_id, result, processing_time)

        logger.info(
            "Transcription job completed job_id=%s audio_duration=%.3f "
            "processing_time=%.3f rtf=%.4f diarization_enabled=%s "
            "conversion_time=%.3f diarization_time=%.3f transcription_time=%.3f "
            "temporary_files=%s temporary_bytes=%s engine=%s",
            transcription_id,
            result.duration_seconds,
            processing_time,
            (
                processing_time / result.duration_seconds
                if result.duration_seconds > 0
                else 0.0
            ),
            claim["use_diarization"],
            result.conversion_seconds,
            result.diarization_seconds,
            result.transcription_seconds,
            result.temporary_files,
            result.temporary_bytes,
            result.engine_metadata,
        )
        return {
            "status": "completed",
            "transcription_id": transcription_id,
            "processing_time": processing_time,
            "word_count": result.word_count,
        }
    except Exception as exc:
        public_error = "Audio exceeds the public duration limit" if isinstance(exc, PublicAudioDurationError) else "Transcription processing failed"
        if claimed:
            try:
                _persist_failed_job(transcription_id, public_error)
            except Exception:
                # A database outage must not expose query parameters through
                # RQ's stored traceback. Recovery reconciles the durable job.
                pass
        logger.error("Transcription job %s failed (%s)", transcription_id, type(exc).__name__)
        # RQ must record failure too. Do not propagate the original exception:
        # its repr/traceback could contain credentials or transcript fragments.
        raise RuntimeError(public_error) from None
    finally:
        if claimed and input_path:
            if not delete_file_idempotently(input_path):
                logger.warning("Input cleanup incomplete for transcription %s", transcription_id)
