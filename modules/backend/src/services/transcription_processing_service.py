"""Pipeline pesado de áudio, importado e executado apenas pelo RQ worker."""

import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .. import engine_registry
from ..utils.audio import convert_to_wav

logger = logging.getLogger(__name__)
_TEMP_DIRECTORY = Path(__file__).resolve().parents[2] / "temp"


class TranscriptionProcessingError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessingResult:
    segments: list[dict]
    duration_seconds: float
    num_speakers: int
    word_count: int


class TranscriptionProcessingService:
    """Coordena FFmpeg, diarização e transcrição usando engines reutilizados."""

    def process_transcription(
        self,
        file_path: str,
        use_diarization: bool,
        transcription_model: str,
    ) -> ProcessingResult:
        _TEMP_DIRECTORY.mkdir(parents=True, exist_ok=True)
        wav_path = _TEMP_DIRECTORY / f"wav_{uuid.uuid4()}.wav"

        try:
            converted_path, duration = convert_to_wav(file_path, str(wav_path))
            if use_diarization:
                segments, num_speakers = self._process_with_diarization(
                    converted_path,
                    transcription_model,
                )
            else:
                segments, num_speakers = self._process_without_diarization(
                    converted_path,
                    duration,
                    transcription_model,
                )

            return ProcessingResult(
                segments=segments,
                duration_seconds=duration,
                num_speakers=num_speakers,
                word_count=sum(len(segment["text"].split()) for segment in segments),
            )
        finally:
            self._remove_file_with_retry(wav_path)

    def _process_with_diarization(
        self,
        wav_path: str,
        transcription_model: str,
    ) -> tuple[list[dict], int]:
        diarization_engine = engine_registry.diarization_engine
        if diarization_engine is None:
            raise TranscriptionProcessingError("Diarization engine is unavailable")

        diarization_result = diarization_engine.diarize(wav_path)
        transcribe = self._get_transcribe_function(transcription_model)
        segments: list[dict] = []

        for segment in diarization_result["segments"]:
            try:
                text = transcribe(
                    wav_path,
                    start=segment["start"],
                    end=segment["end"],
                )
            except Exception:
                logger.exception(
                    "Transcription failed for segment %.2f-%.2f",
                    segment["start"],
                    segment["end"],
                )
                text = "[erro na transcrição]"

            segments.append(
                {
                    "start": segment["start"],
                    "end": segment["end"],
                    "speaker": segment["speaker"],
                    "text": text,
                }
            )

        return segments, diarization_result["num_speakers"]

    def _process_without_diarization(
        self,
        wav_path: str,
        duration: float,
        transcription_model: str,
    ) -> tuple[list[dict], int]:
        text = self._get_transcribe_function(transcription_model)(wav_path)
        return [
            {
                "start": 0.0,
                "end": duration,
                "speaker": "SPEAKER_00",
                "text": text,
            }
        ], 1

    @staticmethod
    def _get_transcribe_function(transcription_model: str):
        if transcription_model == "whisper":
            engine = engine_registry.whisper_engine
        elif transcription_model == "assemblyai":
            engine = engine_registry.assemblyai_engine
        else:
            raise TranscriptionProcessingError(
                f"Unknown transcription model: {transcription_model}"
            )

        if engine is None:
            raise TranscriptionProcessingError(
                f"{transcription_model} engine is unavailable"
            )
        return engine.transcribe_segment

    @staticmethod
    def _remove_file_with_retry(path: Path, attempts: int = 5) -> None:
        for attempt in range(attempts):
            try:
                path.unlink(missing_ok=True)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    logger.warning("Unable to remove temporary WAV %s", path)
                else:
                    time.sleep(0.2)
