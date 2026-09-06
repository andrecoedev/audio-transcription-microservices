"""Jobs RQ de transcrição executados fora do processo FastAPI."""

import logging
import time
from pathlib import Path

from rq.exceptions import NoSuchJobError
from rq.job import Job

from ..api_keys_manager import api_keys_manager
from ..config import apply_persisted_secrets, settings
from ..database import SessionLocal
from ..models import Transcription, TranscriptionJob
from ..services.processing_engines import initialize_processing_engines
from ..services.transcription_processing_service import (
    TranscriptionProcessingService,
)

logger = logging.getLogger(__name__)
_processing_service: TranscriptionProcessingService | None = None


def initialize_worker_engines(
    factories=None,
) -> dict[str, bool]:
    """Inicializa engines uma vez no processo worker, antes de consumir a fila."""
    global _processing_service

    apply_persisted_secrets(api_keys_manager.get_all())
    validation_errors = settings.validate_startup()
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
        _processing_service = TranscriptionProcessingService()
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
            transcription.status = "queued"
            transcription.error_message = None
            queue.enqueue(
                process_transcription_job_sync,
                db_job.transcription_id,
                job_id=rq_job_id,
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


def process_transcription_job_sync(transcription_id: int) -> dict:
    """Executa o pipeline pesado e persiste seu resultado."""
    db = SessionLocal()
    input_path: str | None = None

    try:
        job = (
            db.query(TranscriptionJob)
            .filter(TranscriptionJob.transcription_id == transcription_id)
            .first()
        )
        transcription = db.get(Transcription, transcription_id)
        input_path = job.input_path if job else None

        if not job or not transcription:
            logger.warning("Job or transcription not found for id=%s", transcription_id)
            return {"status": "failed", "error": "Transcription job not found"}

        if job.status in {"completed", "done"}:
            logger.info("Transcription job %s was already completed", transcription_id)
            return {"status": "already_done"}

        started_at = time.time()
        job.status = "processing"
        transcription.status = "processing"
        db.commit()
        logger.info("Transcription job %s started", transcription_id)

        result = get_processing_service().process_transcription(
            file_path=job.input_path,
            use_diarization=job.use_diarization,
            transcription_model=job.transcription_model,
        )
        processing_time = time.time() - started_at

        transcription.duration_seconds = result.duration_seconds
        transcription.transcription_model = job.transcription_model
        transcription.use_diarization = job.use_diarization
        transcription.segments = result.segments
        transcription.num_speakers = result.num_speakers
        transcription.word_count = result.word_count
        transcription.processing_time_seconds = processing_time
        transcription.status = "completed"
        transcription.error_message = None
        job.status = "completed"
        job.error_message = None
        db.commit()

        logger.info(
            "Transcription job %s completed in %.2fs",
            transcription_id,
            processing_time,
        )
        return {
            "status": "completed",
            "transcription_id": transcription_id,
            "processing_time": processing_time,
            "word_count": result.word_count,
        }
    except Exception:
        public_error = "Transcription processing failed"
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
        db.commit()
        logger.exception("Transcription job %s failed", transcription_id)
        return {
            "status": "failed",
            "transcription_id": transcription_id,
            "error": public_error,
        }
    finally:
        if input_path:
            try:
                Path(input_path).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(
                    "Unable to remove input for transcription %s: %s",
                    transcription_id,
                    exc,
                )
        db.close()
