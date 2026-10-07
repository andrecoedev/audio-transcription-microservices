"""Heavy audio pipeline imported and executed only by the RQ worker."""

import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .. import engine_registry
from ..utils.audio import convert_to_wav

logger = logging.getLogger(__name__)
_TEMP_DIRECTORY = Path(__file__).resolve().parents[2] / "temp"


class TranscriptionProcessingError(RuntimeError):
    pass


class PublicAudioDurationError(TranscriptionProcessingError):
    pass


@dataclass(frozen=True)
class ProcessingResult:
    segments: list[dict]
    duration_seconds: float
    num_speakers: int
    word_count: int
    conversion_seconds: float = 0.0
    diarization_seconds: float = 0.0
    transcription_seconds: float = 0.0
    temporary_files: int = 0
    temporary_bytes: int = 0
    engine_metadata: dict[str, str] = field(default_factory=dict)


class TranscriptionProcessingService:
    """Coordinate normalization, diarization and a reusable transcription engine."""

    def __init__(self, cloud_engine=None):
        self.cloud_engine = cloud_engine
        self.usage_observer = None

    def set_usage_observer(self, callback):
        self.usage_observer = callback

    def _observe(self, metric, quantity):
        if self.usage_observer:
            try:
                self.usage_observer(metric, quantity)
            except Exception as exc:
                logger.warning("Processing usage observer failed (%s)", type(exc).__name__)

    def process_transcription(
        self,
        file_path: str,
        use_diarization: bool,
        transcription_model: str,
        max_duration_seconds: int | None = None,
    ) -> ProcessingResult:
        _TEMP_DIRECTORY.mkdir(parents=True, exist_ok=True)
        wav_path = _TEMP_DIRECTORY / f"wav_{uuid.uuid4()}.wav"
        temporary_bytes = 0

        try:
            conversion_started = time.perf_counter()
            converted_path, duration = convert_to_wav(file_path, str(wav_path),
                **({"max_duration_seconds": max_duration_seconds} if max_duration_seconds else {}))
            if max_duration_seconds and duration > max_duration_seconds:
                raise PublicAudioDurationError("Audio exceeds the public duration limit")
            conversion_seconds = time.perf_counter() - conversion_started
            self._observe("audio_seconds", duration)
            temporary_bytes = wav_path.stat().st_size

            if transcription_model == "assemblyai":
                transcription_started = time.perf_counter()
                native = self._get_engine(transcription_model).transcribe_file(
                    converted_path, duration_seconds=duration, use_diarization=use_diarization)
                segments, num_speakers = native["segments"], native["num_speakers"]
                diarization_seconds = 0.0
                transcription_seconds = time.perf_counter() - transcription_started
            elif use_diarization:
                (
                    segments,
                    num_speakers,
                    diarization_seconds,
                    transcription_seconds,
                ) = self._process_with_diarization(
                    converted_path,
                    duration,
                    transcription_model,
                )
            else:
                diarization_seconds = 0.0
                transcription_started = time.perf_counter()
                segments, num_speakers = self._process_without_diarization(
                    converted_path,
                    duration,
                    transcription_model,
                )
                transcription_seconds = time.perf_counter() - transcription_started

            engine = self._get_engine(transcription_model)
            metadata_getter = getattr(engine, "get_metadata", lambda: {})
            return ProcessingResult(
                segments=segments,
                duration_seconds=duration,
                num_speakers=num_speakers,
                word_count=sum(len(segment["text"].split()) for segment in segments),
                conversion_seconds=conversion_seconds,
                diarization_seconds=diarization_seconds,
                transcription_seconds=transcription_seconds,
                temporary_files=1,
                temporary_bytes=temporary_bytes,
                engine_metadata=metadata_getter(),
            )
        finally:
            self._remove_file_with_retry(wav_path)

    def _process_with_diarization(
        self,
        wav_path: str,
        duration: float,
        transcription_model: str,
    ) -> tuple[list[dict], int, float, float]:
        diarization_engine = engine_registry.diarization_engine
        if diarization_engine is None:
            raise TranscriptionProcessingError("Diarization engine is unavailable")

        diarization_started = time.perf_counter()
        diarization_result = diarization_engine.diarize(wav_path)
        diarization_seconds = time.perf_counter() - diarization_started
        transcribe = self._get_engine(transcription_model).transcribe_segment
        segments: list[dict] = []
        transcription_seconds = 0.0

        ordered_segments = sorted(
            diarization_result["segments"],
            key=lambda segment: (segment["start"], segment["end"]),
        )
        for segment in ordered_segments:
            start = max(0.0, float(segment["start"]))
            end = min(duration, float(segment["end"]))
            if end <= start:
                logger.warning(
                    "Ignoring invalid diarization timestamps start=%.3f end=%.3f",
                    start,
                    end,
                )
                continue
            transcription_started = time.perf_counter()
            try:
                text = transcribe(wav_path, start=start, end=end)
            except Exception as exc:
                logger.error(
                    "Transcription failed for segment %.2f-%.2f (%s)",
                    start,
                    end,
                    type(exc).__name__,
                )
                text = "[erro na transcrição]"
            transcription_seconds += time.perf_counter() - transcription_started
            segments.append(
                {
                    "start": start,
                    "end": end,
                    "speaker": segment["speaker"],
                    "text": text,
                }
            )

        return (
            segments,
            int(diarization_result["num_speakers"]),
            diarization_seconds,
            transcription_seconds,
        )

    def _process_without_diarization(
        self,
        wav_path: str,
        duration: float,
        transcription_model: str,
    ) -> tuple[list[dict], int]:
        text = self._get_engine(transcription_model).transcribe_segment(
            wav_path,
            start=0.0,
            end=duration,
        )
        return [
            {
                "start": 0.0,
                "end": duration,
                "speaker": "SPEAKER_00",
                "text": text,
            }
        ], 1

    def _get_engine(self, transcription_model: str):
        if transcription_model == "whisper":
            engine = engine_registry.whisper_engine
        elif transcription_model == "assemblyai":
            engine = self.cloud_engine if self.cloud_engine is not None else engine_registry.assemblyai_engine
        else:
            raise TranscriptionProcessingError(
                f"Unknown transcription model: {transcription_model}"
            )
        if engine is None:
            raise TranscriptionProcessingError(
                f"{transcription_model} engine is unavailable"
            )
        return engine

    @staticmethod
    def _remove_file_with_retry(path: Path, attempts: int = 5) -> None:
        for attempt in range(attempts):
            try:
                path.unlink(missing_ok=True)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    logger.warning("Unable to remove temporary normalized audio")
                else:
                    time.sleep(0.2)
