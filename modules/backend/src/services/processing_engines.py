"""Initialize and retain engines exclusively in the RQ worker process."""

import logging
from functools import partial
from collections.abc import Callable
from typing import Any

from .. import engine_registry
from ..config import settings

logger = logging.getLogger(__name__)


def _default_factories(providers: set[str]) -> dict[str, Callable[..., Any]]:
    factories: dict[str, Callable[..., Any]] = {}
    if "whisper" in providers:
        from .faster_whisper_engine import FasterWhisperEngine
        factories["whisper"] = FasterWhisperEngine
    if "diarization" in providers and settings.HF_TOKEN:
        from .diarization_engine import DiarizationEngine

        factories["diarization"] = DiarizationEngine
    if "assemblyai" in providers and settings.AAI_API_KEY:
        from .assemblyai_engine import AssemblyAIEngine

        factories["assemblyai"] = partial(AssemblyAIEngine,
            http_timeout=settings.AAI_HTTP_TIMEOUT_SECONDS,
            timeout_seconds=settings.AAI_TIMEOUT_SECONDS,
            poll_interval=settings.AAI_POLL_INTERVAL_SECONDS)
    if "gemini" in providers and settings.GEMINI_API_KEY:
        from .meeting_minutes import MeetingMinutesGenerator

        factories["gemini"] = MeetingMinutesGenerator
    return factories


def initialize_processing_engines(
    hf_token: str | None,
    aai_api_key: str | None,
    gemini_api_key: str | None,
    factories: dict[str, Callable[..., Any]] | None = None,
    providers: set[str] | None = None,
) -> dict[str, bool]:
    """Initialize once per work-horse process; supervised jobs use separate children."""
    providers = providers if providers is not None else {"whisper", "diarization", "assemblyai", "gemini"}
    factories = factories if factories is not None else _default_factories(providers)

    if "diarization" in providers and hf_token and engine_registry.diarization_engine is None:
        try:
            engine_registry.diarization_engine = factories["diarization"](hf_token)
            logger.info("Diarization engine initialized in worker")
        except Exception as exc:
            logger.error("Unable to initialize diarization engine in worker (%s)", type(exc).__name__)
    elif "diarization" in providers and not hf_token:
        logger.warning("HF_TOKEN is not configured; diarization is unavailable")

    if "whisper" in providers and engine_registry.whisper_engine is None:
        try:
            engine_registry.whisper_engine = factories["whisper"](hf_token)
            metadata_getter = getattr(
                engine_registry.whisper_engine,
                "get_metadata",
                lambda: {"engine": "faster-whisper"},
            )
            logger.info("Whisper engine ready in worker: %s", metadata_getter())
        except Exception as exc:
            logger.error("Unable to initialize Whisper engine in worker (%s)", type(exc).__name__)

    if "assemblyai" in providers and aai_api_key and engine_registry.assemblyai_engine is None:
        try:
            engine_registry.assemblyai_engine = factories["assemblyai"](aai_api_key)
            logger.info("AssemblyAI engine initialized in worker")
        except Exception as exc:
            logger.error("Unable to initialize AssemblyAI engine in worker (%s)", type(exc).__name__)

    if "gemini" in providers and gemini_api_key and engine_registry.meeting_minutes_generator is None:
        try:
            engine_registry.meeting_minutes_generator = factories["gemini"](
                gemini_api_key
            )
            logger.info("Gemini client initialized in worker")
        except Exception as exc:
            logger.error("Unable to initialize Gemini client in worker (%s)", type(exc).__name__)

    return {
        "diarization": engine_registry.diarization_engine is not None,
        "whisper": engine_registry.whisper_engine is not None,
        "assemblyai": engine_registry.assemblyai_engine is not None,
        "gemini": engine_registry.meeting_minutes_generator is not None,
    }
