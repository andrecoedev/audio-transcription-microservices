"""Healthchecks leves da API e disponibilidade externa do processamento."""

import logging

from fastapi import APIRouter, Depends, Response
from rq import Worker
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..workers.config import (
    TRANSCRIPTION_QUEUE_NAME,
    get_redis_connection,
    is_redis_available,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _processing_status() -> dict:
    try:
        connection = get_redis_connection()
        redis_available = is_redis_available(connection)
    except Exception as exc:
        logger.warning("Redis healthcheck failed: %s", exc)
        return {
            "redis": "unavailable",
            "queue": TRANSCRIPTION_QUEUE_NAME,
            "worker_available": False,
            "worker_count": 0,
        }
    worker_count = 0
    if redis_available:
        try:
            worker_count = len(Worker.all(connection=connection))
        except Exception as exc:
            logger.warning("Unable to inspect RQ workers: %s", exc)

    return {
        "redis": "connected" if redis_available else "unavailable",
        "worker_available": worker_count > 0,
        "worker_count": worker_count,
        "queue": TRANSCRIPTION_QUEUE_NAME,
    }


def _configured_models(processing: dict) -> dict:
    worker_device = "worker-managed" if processing["worker_available"] else "worker-offline"
    return {
        "diarization": {
            "configured": bool(settings.HF_TOKEN),
            "loaded": None,
            "device": worker_device,
        },
        "whisper": {
            "configured": bool(settings.WHISPER_MODEL),
            "loaded": None,
            "device": worker_device,
        },
        "assemblyai": {
            "configured": bool(settings.AAI_API_KEY),
            "loaded": None,
            "device": worker_device,
        },
        "gemini": {
            "configured": bool(settings.GEMINI_API_KEY),
            "loaded": None,
            "device": worker_device,
        },
    }


@router.get("/")
async def root():
    return {
        "message": "Transcription API",
        "version": "2.1.0",
        "docs": "/docs",
    }


@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Verifica API, banco, Redis e presença de workers sem importar ML."""
    database_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        database_status = "unavailable"
        logger.warning("Database healthcheck failed: %s", exc)

    processing = _processing_status()
    return {
        "status": (
            "ok"
            if database_status == "connected" and processing["redis"] == "connected"
            else "degraded"
        ),
        "api": "ready",
        "database": database_status,
        "processing": processing,
        "models": _configured_models(processing),
    }


@router.get("/system/gpu", deprecated=True)
async def gpu_diagnostics(response: Response):
    """Compatibilidade: diagnóstico GPU pertence agora ao processo worker."""
    response.headers["Deprecation"] = "true"
    return {
        "deprecated": True,
        "detail": "GPU diagnostics moved to the RQ worker logs.",
        "scope": "worker",
    }
