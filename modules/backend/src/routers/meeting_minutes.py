"""API de atas: valida e delega a geração de IA ao RQ worker."""

import asyncio
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from rq import Worker
from sqlalchemy.orm import Session

from ..authorization import enforce_transcription_access
from ..config import settings
from ..database import get_db
from ..models import Transcription
from ..schemas import MeetingMinutesRequest
from ..security import TokenData, require_scope_when
from ..workers.config import get_transcription_queue, is_redis_available

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_available_queue():
    try:
        queue = get_transcription_queue()
        if not is_redis_available(queue.connection):
            raise RuntimeError("Redis unavailable")
        if not Worker.all(connection=queue.connection):
            raise RuntimeError("RQ worker unavailable")
        return queue
    except Exception:
        logger.warning("Meeting minutes queue unavailable")
        raise HTTPException(
            status_code=503,
            detail="Processing worker is temporarily unavailable",
        ) from None


async def _wait_for_result(job):
    deadline = time.monotonic() + settings.MEETING_MINUTES_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        job_status = job.get_status(refresh=True)
        job_status = getattr(job_status, "value", job_status)
        if job_status == "finished":
            return job.return_value(refresh=True)
        if job_status in {"failed", "stopped", "canceled"}:
            logger.error("Meeting minutes RQ job %s failed", job.id)
            raise HTTPException(
                status_code=502,
                detail="Meeting minutes processing failed",
            )
        await asyncio.sleep(0.25)

    logger.error("Meeting minutes RQ job %s timed out", job.id)
    raise HTTPException(status_code=504, detail="Meeting minutes processing timed out")


@router.post("/meeting-minutes/generate")
async def generate_meeting_minutes(
    request: MeetingMinutesRequest,
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(
        require_scope_when("meeting_minutes", settings.AUTH_PROTECT_PROCESSING)
    ),
):
    """Preserva o contrato síncrono, mas executa Gemini no processo worker."""
    if not (settings.GEMINI_API_KEY_CONFIGURED or settings.GEMINI_API_KEY):
        raise HTTPException(
            status_code=503,
            detail="Meeting minutes generator is not configured",
        )

    transcription = db.get(Transcription, request.transcription_id)
    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")
    enforce_transcription_access(db, request.transcription_id, current_user)
    if transcription.status != "completed":
        raise HTTPException(
            status_code=400,
            detail="Only completed transcriptions can be used",
        )

    queue = _get_available_queue()
    try:
        job = queue.enqueue(
            "src.workers.meeting_minutes_worker.process_meeting_minutes_sync",
            request.transcription_id,
            {
                "title": request.title,
                "date": request.date,
                "participants": request.participants,
            },
            job_id=f"meeting_minutes_{request.transcription_id}_{uuid.uuid4().hex}",
            job_timeout=settings.MEETING_MINUTES_TIMEOUT_SECONDS,
            result_ttl=settings.MEETING_MINUTES_TIMEOUT_SECONDS,
        )
        logger.info(
            "Meeting minutes job queued for transcription %s",
            request.transcription_id,
        )
    except Exception as exc:
        logger.error(
            "Unable to enqueue meeting minutes for transcription %s (%s)",
            request.transcription_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Processing worker is temporarily unavailable",
        )

    return await _wait_for_result(job)


@router.get("/meeting-minutes/status")
async def get_meeting_minutes_status(
    current_user: Optional[TokenData] = Depends(
        require_scope_when("meeting_minutes", settings.AUTH_PROTECT_READS)
    ),
):
    configured = settings.GEMINI_API_KEY_CONFIGURED or bool(settings.GEMINI_API_KEY)
    worker_available = False
    if configured:
        try:
            queue = get_transcription_queue()
            worker_available = is_redis_available(queue.connection) and bool(
                Worker.all(connection=queue.connection)
            )
        except Exception:
            logger.warning("Unable to inspect meeting minutes worker")

    return {
        "available": configured and worker_available,
        "configured": configured,
        "worker_available": worker_available,
        "config": {"provider": "gemini", "execution": "rq-worker"},
    }
