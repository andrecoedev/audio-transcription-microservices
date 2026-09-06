"""Faster-Whisper adapter used only by the RQ worker."""

import logging
import math
import time
from collections.abc import Callable, Iterable
from typing import Any

from ..config import settings
from ..utils.audio import decode_audio_segment, probe_audio_duration

logger = logging.getLogger(__name__)


class FasterWhisperEngineError(RuntimeError):
    pass


class FasterWhisperEngine:
    """Stable text contract over CTranslate2-based Faster-Whisper."""

    engine_name = "faster-whisper"

    def __init__(
        self,
        hf_token: str | None = None,
        *,
        model_name: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        language: str | None = None,
        model_factory: Callable[..., Any] | None = None,
        cuda_device_count: Callable[[], int] | None = None,
        supported_compute_types: Callable[[str], set[str]] | None = None,
        segment_decoder: Callable[..., Any] = decode_audio_segment,
        duration_probe: Callable[[str], float] = probe_audio_duration,
    ) -> None:
        self.hf_token = hf_token
        self.model_name = model_name or settings.WHISPER_MODEL
        self.language = language or settings.WHISPER_LANGUAGE
        self.beam_size = settings.WHISPER_BEAM_SIZE
        self.max_decode_chunk_seconds = settings.WHISPER_MAX_DECODE_CHUNK_SECONDS
        self._decode_segment = segment_decoder
        self._probe_duration = duration_probe

        if cuda_device_count is None:
            cuda_device_count = self._get_cuda_device_count
        self.device = self.resolve_device(
            device or settings.WHISPER_DEVICE,
            force_cpu=settings.FORCE_CPU,
            cuda_device_count=cuda_device_count,
        )

        if supported_compute_types is None:
            supported_compute_types = self._get_supported_compute_types
        self.compute_type = self.resolve_compute_type(
            compute_type or settings.WHISPER_COMPUTE_TYPE,
            self.device,
            supported_compute_types,
        )

        if model_factory is None:
            from faster_whisper import WhisperModel

            model_factory = WhisperModel

        started_at = time.perf_counter()
        try:
            self.model = model_factory(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=settings.WHISPER_CPU_THREADS,
                use_auth_token=self.hf_token or None,
            )
        except Exception as exc:
            raise FasterWhisperEngineError(
                "Unable to initialize Faster-Whisper"
            ) from exc

        logger.info(
            "Whisper engine initialized engine=%s model=%s device=%s "
            "compute_type=%s language=%s load_seconds=%.3f",
            self.engine_name,
            self.model_name,
            self.device,
            self.compute_type,
            self.language,
            time.perf_counter() - started_at,
        )

    @staticmethod
    def _get_cuda_device_count() -> int:
        import ctranslate2

        return ctranslate2.get_cuda_device_count()

    @staticmethod
    def _get_supported_compute_types(device: str) -> set[str]:
        import ctranslate2

        return set(ctranslate2.get_supported_compute_types(device))

    @staticmethod
    def resolve_device(
        requested: str,
        *,
        force_cpu: bool,
        cuda_device_count: Callable[[], int],
    ) -> str:
        if force_cpu or requested == "cpu":
            return "cpu"
        cuda_available = cuda_device_count() > 0
        if requested == "cuda":
            if not cuda_available:
                raise FasterWhisperEngineError(
                    "WHISPER_DEVICE=cuda but CTranslate2 found no CUDA device"
                )
            return "cuda"
        if requested == "auto":
            return "cuda" if cuda_available else "cpu"
        raise FasterWhisperEngineError(f"Unsupported Whisper device: {requested}")

    @staticmethod
    def resolve_compute_type(
        requested: str,
        device: str,
        supported_compute_types: Callable[[str], set[str]],
    ) -> str:
        selected = (
            "float16" if device == "cuda" else "int8"
        ) if requested == "auto" else requested
        if selected == "default":
            return selected
        supported = supported_compute_types(device)
        if selected not in supported:
            raise FasterWhisperEngineError(
                f"Compute type {selected!r} is not supported on {device}; "
                f"available={sorted(supported)}"
            )
        return selected

    def transcribe_segment(
        self,
        audio_path: str,
        start: float = 0.0,
        end: float | None = None,
    ) -> str:
        if start < 0:
            raise ValueError("Audio segment start cannot be negative")
        if end is None:
            end = self._probe_duration(audio_path)
        if end <= start:
            raise ValueError("Audio segment end must be greater than start")

        texts: list[str] = []
        current_start = start
        while current_start < end:
            window_duration = min(
                self.max_decode_chunk_seconds,
                end - current_start,
            )
            pcm = self._decode_segment(
                audio_path,
                start=current_start,
                duration=window_duration,
            )
            if len(pcm):
                try:
                    segments, _ = self.model.transcribe(
                        pcm,
                        language=None if self.language == "auto" else self.language,
                        task="transcribe",
                        beam_size=self.beam_size,
                        temperature=0.0,
                        condition_on_previous_text=False,
                        vad_filter=False,
                    )
                    texts.extend(self._consume_segments(segments, window_duration))
                except FasterWhisperEngineError:
                    raise
                except Exception as exc:
                    raise FasterWhisperEngineError(
                        "Faster-Whisper inference failed"
                    ) from exc
            current_start = math.fsum((current_start, window_duration))

        return " ".join(texts).strip()

    @staticmethod
    def _consume_segments(
        segments: Iterable[Any],
        window_duration: float,
    ) -> list[str]:
        texts: list[str] = []
        previous_start = 0.0
        for segment in segments:
            segment_start = float(segment.start)
            segment_end = float(segment.end)
            if (
                segment_start < -0.05
                or segment_end < segment_start
                or segment_start + 0.05 < previous_start
                or segment_end > window_duration + 1.0
            ):
                raise FasterWhisperEngineError(
                    "Faster-Whisper returned invalid segment timestamps"
                )
            previous_start = max(previous_start, segment_start)
            text = str(segment.text).strip()
            if text:
                texts.append(text)
        return texts

    def get_device(self) -> str:
        return self.device

    def get_metadata(self) -> dict[str, str]:
        return {
            "engine": self.engine_name,
            "model": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "language": self.language,
        }
