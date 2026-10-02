"""Initialize and retain engines exclusively in the RQ worker process."""

import logging
from collections.abc import Callable
from typing import Any

from .. import engine_registry
from ..config import settings

logger = logging.getLogger(__name__)


def _default_factories() -> dict[str, Callable[..., Any]]:
    from .faster_whisper_engine import FasterWhisperEngine

    factories: dict[str, Callable[..., Any]] = {"whisper": FasterWhisperEngine}
    if settings.HF_TOKEN:
        from .diarization_engine import DiarizationEngine

        factories["diarization"] = DiarizationEngine
    if settings.AAI_API_KEY:
        from .assemblyai_engine import AssemblyAIEngine

        factories["assemblyai"] = AssemblyAIEngine
    if settings.GEMINI_API_KEY:
        from .meeting_minutes import MeetingMinutesGenerator

        factories["gemini"] = MeetingMinutesGenerator
    return factories


def initialize_processing_engines(
    hf_token: str | None,
    aai_api_key: str | None,
    gemini_api_key: str | None,
    factories: dict[str, Callable[..., Any]] | None = None,
) -> dict[str, bool]:
    """Initialize each configured engine once and reuse it across worker jobs."""
    factories = factories or _default_factories()

    if hf_token and engine_registry.diarization_engine is None:
        try:
            engine_registry.diarization_engine = factories["diarization"](hf_token)
            logger.info("Diarization engine initialized in worker")
        except Exception as exc:
            logger.error("Unable to initialize diarization engine in worker (%s)", type(exc).__name__)
    elif not hf_token:
        logger.warning("HF_TOKEN is not configured; diarization is unavailable")

    if engine_registry.whisper_engine is None:
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

    if aai_api_key and engine_registry.assemblyai_engine is None:
        try:
            engine_registry.assemblyai_engine = factories["assemblyai"](aai_api_key)
            logger.info("AssemblyAI engine initialized in worker")
        except Exception as exc:
            logger.error("Unable to initialize AssemblyAI engine in worker (%s)", type(exc).__name__)

    if gemini_api_key and engine_registry.meeting_minutes_generator is None:
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
