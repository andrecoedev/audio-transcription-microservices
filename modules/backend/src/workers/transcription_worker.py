"""
Worker de processamento de transcrição com RQ.

Consome jobs da fila Redis e executa o processamento.
Este worker roda em um processo separado.
"""

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from rq.exceptions import NoSuchJobError
from rq.job import Job

from .. import engine_registry
from ..config import settings
from ..database import SessionLocal
from ..models import Transcription, TranscriptionJob
from ..utils.audio import convert_to_wav, remove_temp_file_with_retry
from ..routers.transcribe import _process_with_diarization, _process_without_diarization

logger = logging.getLogger(__name__)
_TEMP_DIRECTORY = Path(__file__).resolve().parents[2] / "temp"


def initialize_worker_engines() -> None:
    """Carrega no processo RQ apenas os engines necessários para transcrição."""
    from ..api_keys_manager import api_keys_manager
    from ..config import apply_persisted_secrets
    from ..services.diarization_engine import DiarizationEngine
    from ..services.transcription_engine import AssemblyAIEngine, WhisperEngine
    from ..utils.gpu_utils import log_device_info, optimize_gpu_settings

    apply_persisted_secrets(api_keys_manager.get_all())
    validation_errors = settings.validate_startup()
    if validation_errors:
        raise RuntimeError("Invalid worker configuration: " + "; ".join(validation_errors))

    log_device_info()
    optimize_gpu_settings()

    if settings.HF_TOKEN:
        if engine_registry.diarization_engine is None:
            try:
                engine_registry.diarization_engine = DiarizationEngine(settings.HF_TOKEN)
                logger.info("Diarization engine loaded in RQ worker")
            except Exception:
                logger.exception("Unable to load diarization engine in RQ worker")
        if engine_registry.whisper_engine is None:
            try:
                engine_registry.whisper_engine = WhisperEngine(settings.HF_TOKEN)
                logger.info("Whisper engine loaded in RQ worker")
            except Exception:
                logger.exception("Unable to load Whisper engine in RQ worker")
    else:
        logger.warning("HF_TOKEN is not configured; Whisper and diarization are unavailable")

    if settings.AAI_API_KEY:
        if engine_registry.assemblyai_engine is None:
            try:
                engine_registry.assemblyai_engine = AssemblyAIEngine(settings.AAI_API_KEY)
                logger.info("AssemblyAI engine loaded in RQ worker")
            except Exception:
                logger.exception("Unable to load AssemblyAI engine in RQ worker")
    else:
        logger.warning("AAI_API_KEY is not configured; AssemblyAI is unavailable")


def recover_pending_jobs(queue) -> int:
    """Reconcilia jobs persistidos com o RQ sem duplicar jobs ainda ativos."""
    db = SessionLocal()
    recovered = 0
    try:
        # O cleanup do RQ move entradas "started" expiradas para o estado terminal;
        # jobs realmente ativos permanecem protegidos contra reenfileiramento.
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
    """
    Processa um job de transcrição de forma síncrona (chamado por RQ worker).
    
    RQ não suporta async nativamente, então usamos asyncio.run() para executar
    a lógica assíncrona.
    
    Args:
        transcription_id: ID da transcrição a processar
        
    Returns:
        Dict com status e resultado do processamento
    """
    return asyncio.run(_process_transcription_job_async(transcription_id))


async def _process_transcription_job_async(transcription_id: int) -> dict:
    """Processa um job de transcrição pendente e persiste o resultado."""
    db = SessionLocal()
    temp_wav_path: Optional[str] = None
    input_path: Optional[str] = None

    try:
        job = (
            db.query(TranscriptionJob)
            .filter(TranscriptionJob.transcription_id == transcription_id)
            .first()
        )
        transcription = (
            db.query(Transcription)
            .filter(Transcription.id == transcription_id)
            .first()
        )

        input_path = job.input_path if job else None

        if not job or not transcription:
            logger.warning(f"Job ou transcrição não encontrado para id={transcription_id}")
            return {"status": "failed", "error": "Job ou transcrição não encontrado"}

        if job.status in {"completed", "done"}:
            logger.info(f"Job {transcription_id} já foi processado")
            return {"status": "already_done"}

        start_time = time.time()
        loop = asyncio.get_running_loop()
        # Atualiza status
        job.status = "processing"
        transcription.status = "processing"
        db.commit()
        logger.info(f"Processando transcrição {transcription_id}")

        # Converte para WAV
        wav_output_path = str(_TEMP_DIRECTORY / f"wav_{uuid.uuid4()}.wav")
        temp_wav_path, duration = await loop.run_in_executor(
            None,
            convert_to_wav,
            input_path,
            wav_output_path,
        )

        # Processa com ou sem diarização
        if job.use_diarization:
            segments, num_speakers = await _process_with_diarization(
                temp_wav_path,
                job.transcription_model,
                loop,
            )
        else:
            segments, num_speakers = await _process_without_diarization(
                temp_wav_path,
                duration,
                job.transcription_model,
                loop,
            )

        # Calcula estatísticas
        word_count = sum(len(seg["text"].split()) for seg in segments)
        processing_time = time.time() - start_time

        # Persiste resultado
        transcription.duration_seconds = duration
        transcription.transcription_model = job.transcription_model
        transcription.use_diarization = job.use_diarization
        transcription.segments = segments
        transcription.num_speakers = num_speakers
        transcription.word_count = word_count
        transcription.processing_time_seconds = processing_time
        transcription.status = "completed"
        transcription.error_message = None

        job.status = "completed"
        job.error_message = None
        db.commit()

        logger.info("Transcription job %s completed in %.2fs", transcription_id, processing_time)
        return {
            "status": "completed",
            "transcription_id": transcription_id,
            "processing_time": processing_time,
            "word_count": word_count,
        }

    except Exception:
        public_error = "Transcription processing failed"
        # Registra erro no banco
        transcription = (
            db.query(Transcription)
            .filter(Transcription.id == transcription_id)
            .first()
        )
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
        # Limpeza de arquivos temporários
        await remove_temp_file_with_retry(input_path)
        await remove_temp_file_with_retry(temp_wav_path)
        db.close()
