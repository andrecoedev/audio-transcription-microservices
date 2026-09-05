"""Configuração centralizada do Redis e da fila RQ."""

import logging

from redis import Redis
from rq import Queue

from ..config import settings

logger = logging.getLogger(__name__)

TRANSCRIPTION_QUEUE_NAME = "transcriptions"


def get_redis_url() -> str:
    return settings.REDIS_URL


def get_redis_connection() -> Redis:
    return Redis.from_url(get_redis_url(), decode_responses=False)


def get_transcription_queue(connection: Redis | None = None) -> Queue:
    return Queue(
        TRANSCRIPTION_QUEUE_NAME,
        connection=connection or get_redis_connection(),
    )


def is_redis_available(connection: Redis | None = None) -> bool:
    try:
        (connection or get_redis_connection()).ping()
        return True
    except Exception as exc:
        logger.warning("Redis unavailable: %s", exc)
        return False
