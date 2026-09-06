"""AssemblyAI adapter isolated from local Whisper implementations."""

import logging
import os
import time
import uuid
from pathlib import Path

import assemblyai as aai
from pydub import AudioSegment

logger = logging.getLogger(__name__)
_TEMP_DIRECTORY = Path(__file__).resolve().parents[2] / "temp"


class AssemblyAIEngine:
    """Cloud transcription adapter preserving the existing text contract."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        aai.settings.api_key = self.api_key
        self.config = aai.TranscriptionConfig(language_code="pt")
        self.transcriber = aai.Transcriber(config=self.config)
        logger.info("AssemblyAI engine initialized in worker")

    def transcribe_segment(
        self,
        audio_path: str,
        start: float = 0.0,
        end: float | None = None,
    ) -> str:
        started_at = time.perf_counter()
        audio = AudioSegment.from_file(audio_path)
        total_duration = len(audio) / 1000.0
        bounded_end = total_duration if end is None else min(end, total_duration)
        if start < 0 or start >= bounded_end:
            raise ValueError("Invalid AssemblyAI audio segment")

        _TEMP_DIRECTORY.mkdir(parents=True, exist_ok=True)
        segment_path = _TEMP_DIRECTORY / f"assemblyai_{uuid.uuid4().hex}.wav"
        try:
            audio[int(start * 1000) : int(bounded_end * 1000)].export(
                segment_path,
                format="wav",
            )
            transcript = self.transcriber.transcribe(str(segment_path))
            text = transcript.text.strip() if transcript.text else ""
            logger.info(
                "AssemblyAI segment completed duration_seconds=%.3f "
                "processing_seconds=%.3f",
                bounded_end - start,
                time.perf_counter() - started_at,
            )
            return text
        finally:
            try:
                os.remove(segment_path)
            except FileNotFoundError:
                pass

    def get_device(self) -> str:
        return "cloud"
