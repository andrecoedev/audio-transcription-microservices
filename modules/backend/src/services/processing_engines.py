"""Inicializa e mantém os engines usados exclusivamente pelo processo worker."""

import logging
from collections.abc import Callable
from typing import Any

from .. import engine_registry

logger = logging.getLogger(__name__)


def initialize_processing_engines(
    hf_token: str | None,
    aai_api_key: str | None,
    gemini_api_key: str | None,
    factories: dict[str, Callable[..., Any]] | None = None,
) -> dict[str, bool]:
    """Inicializa cada engine uma única vez e reutiliza as instâncias existentes."""
    if factories is None:
        from .diarization_engine import DiarizationEngine
        from .meeting_minutes import MeetingMinutesGenerator
        from .transcription_engine import AssemblyAIEngine, WhisperEngine

        factories = {
            "diarization": DiarizationEngine,
            "whisper": WhisperEngine,
            "assemblyai": AssemblyAIEngine,
            "gemini": MeetingMinutesGenerator,
        }

    if hf_token:
        if engine_registry.diarization_engine is None:
            try:
                engine_registry.diarization_engine = factories["diarization"](hf_token)
                logger.info("Diarization engine initialized in worker")
            except Exception:
                logger.exception("Unable to initialize diarization engine in worker")

        if engine_registry.whisper_engine is None:
            try:
                engine_registry.whisper_engine = factories["whisper"](hf_token)
                logger.info("Whisper engine initialized in worker")
            except Exception:
                logger.exception("Unable to initialize Whisper engine in worker")
    else:
        logger.warning("HF_TOKEN is not configured in worker")

    if aai_api_key and engine_registry.assemblyai_engine is None:
        try:
            engine_registry.assemblyai_engine = factories["assemblyai"](aai_api_key)
            logger.info("AssemblyAI engine initialized in worker")
        except Exception:
            logger.exception("Unable to initialize AssemblyAI engine in worker")

    if gemini_api_key and engine_registry.meeting_minutes_generator is None:
        try:
            engine_registry.meeting_minutes_generator = factories["gemini"](
                gemini_api_key
            )
            logger.info("Gemini client initialized in worker")
        except Exception:
            logger.exception("Unable to initialize Gemini client in worker")

    return {
        "diarization": engine_registry.diarization_engine is not None,
        "whisper": engine_registry.whisper_engine is not None,
        "assemblyai": engine_registry.assemblyai_engine is not None,
        "gemini": engine_registry.meeting_minutes_generator is not None,
    }
