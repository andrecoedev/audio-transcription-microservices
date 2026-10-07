"""AssemblyAI adapter for full-file transcription and native diarization."""

import logging
import math
import re
import time
from typing import Any

import assemblyai as aai

logger = logging.getLogger(__name__)
_TRANSCRIPT_ID = re.compile(r"(?=.{1,128}$)[A-Za-z0-9-]+\Z")
_TIMESTAMP_TOLERANCE_SECONDS = 0.1


def _transcript_usage(
    transcript: dict[str, Any], transcript_id: str, use_diarization: bool
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "phase": "polled",
        "status": (
            transcript.get("status")
            if transcript.get("status") in {"completed", "error"}
            else "unknown"
        ),
        "model": "universal-2",
        "use_diarization": bool(use_diarization),
    }
    provider_id = transcript.get("id", transcript_id)
    if (
        isinstance(provider_id, str)
        and _TRANSCRIPT_ID.fullmatch(provider_id)
        and any(c.isalnum() for c in provider_id)
    ):
        event["provider_id"] = provider_id
    duration = transcript.get("audio_duration")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration >= 0:
        try:
            finite = math.isfinite(duration)
        except (OverflowError, TypeError):
            finite = False
        if finite:
            event["audio_duration_seconds"] = duration
    return event


class AssemblyAIProcessingError(RuntimeError):
    """Safe provider failure with a stable, non-sensitive category."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"AssemblyAI processing failed ({code})")


class AssemblyAIEngine:
    """Submit a normalized file once and map the completed response to app data."""

    def __init__(
        self,
        api_key: str,
        *,
        http_timeout: float = 30.0,
        timeout_seconds: float = 180.0,
        poll_interval: float = 3.0,
    ):
        if not api_key:
            raise AssemblyAIProcessingError("credential")
        if http_timeout <= 0 or timeout_seconds <= 0 or poll_interval <= 0:
            raise ValueError("AssemblyAI timeout values must be positive")

        self.http_timeout = float(http_timeout)
        self.timeout_seconds = float(timeout_seconds)
        self.poll_interval = float(poll_interval)
        self._usage_observer = None
        self.client = aai.Client(
            settings=aai.Settings(
                api_key=api_key,
                base_url="https://api.assemblyai.com",
                http_timeout=self.http_timeout,
                polling_interval=self.poll_interval,
            )
        )
        self.transcriber = aai.Transcriber(client=self.client)
        logger.info("AssemblyAI engine initialized in worker")

    def set_usage_observer(self, callback) -> None:
        """Set an optional observer for safe provider usage metadata."""
        self._usage_observer = callback

    def _observe_usage(self, event: dict[str, Any]) -> None:
        if self._usage_observer is None:
            return
        try:
            self._usage_observer(event)
        except Exception as exc:
            logger.warning("Provider usage observer failed (%s)", type(exc).__name__)

    def transcribe_file(
        self,
        audio_path: str,
        duration_seconds: float,
        use_diarization: bool,
    ) -> dict[str, Any]:
        """Transcribe a whole file and return normalized segments and speakers."""
        if not math.isfinite(duration_seconds) or duration_seconds < 0:
            raise AssemblyAIProcessingError("invalid_response")

        config = aai.TranscriptionConfig(
            language_code="pt",
            speaker_labels=use_diarization,
            raw_transcription_config=aai.RawTranscriptionConfig(
                speech_models=["universal-2"]
            ),
        )
        deadline = time.monotonic() + self.timeout_seconds
        self._observe_usage({
            "phase": "submitted", "status": "unknown", "model": "universal-2",
            "use_diarization": bool(use_diarization),
        })
        try:
            submitted = self.transcriber.submit(audio_path, config=config)
        except Exception as exc:
            raise AssemblyAIProcessingError(_failure_code(exc)) from None

        transcript_id = getattr(submitted, "id", None)
        if (
            not isinstance(transcript_id, str)
            or not _TRANSCRIPT_ID.fullmatch(transcript_id)
            or not any(character.isalnum() for character in transcript_id)
        ):
            raise AssemblyAIProcessingError("invalid_response")

        try:
            transcript = self._poll(transcript_id, deadline)
        except AssemblyAIProcessingError:
            self._observe_usage({
                "phase": "polled", "status": "unknown", "model": "universal-2",
                "use_diarization": bool(use_diarization), "provider_id": transcript_id,
            })
            raise
        self._observe_usage(_transcript_usage(transcript, transcript_id, use_diarization))
        if transcript.get("status") != "completed":
            code = _state_error_code(transcript.get("error"))
            raise AssemblyAIProcessingError(code)

        if use_diarization:
            return self._utterance_result(transcript, duration_seconds)
        return self._word_result(transcript, duration_seconds)

    def _poll(self, transcript_id: str, deadline: float) -> dict[str, Any]:
        path = f"/v2/transcript/{transcript_id}"
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssemblyAIProcessingError("timeout")
            try:
                response = self.client.http_client.get(
                    path,
                    timeout=min(self.http_timeout, remaining),
                )
                response.raise_for_status()
                transcript = response.json()
            except Exception as exc:
                raise AssemblyAIProcessingError(_failure_code(exc)) from None

            if not isinstance(transcript, dict):
                raise AssemblyAIProcessingError("invalid_response")
            status = transcript.get("status")
            if status in {"completed", "error"}:
                return transcript
            if status not in {"queued", "processing"}:
                raise AssemblyAIProcessingError("invalid_response")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssemblyAIProcessingError("timeout")
            time.sleep(min(self.poll_interval, remaining))

    @staticmethod
    def _utterance_result(
        transcript: dict[str, Any], duration_seconds: float
    ) -> dict[str, Any]:
        utterances = transcript.get("utterances")
        if not isinstance(utterances, list):
            raise AssemblyAIProcessingError("invalid_response")
        if not utterances:
            if transcript.get("text") != "":
                raise AssemblyAIProcessingError("invalid_response")
            return {"segments": [], "num_speakers": 0}

        speaker_ids: dict[str, str] = {}
        segments = []
        for utterance in utterances:
            if not isinstance(utterance, dict):
                raise AssemblyAIProcessingError("invalid_response")
            text = utterance.get("text")
            speaker = utterance.get("speaker")
            if not isinstance(text, str) or not text.strip() or not isinstance(speaker, str) or not speaker:
                raise AssemblyAIProcessingError("invalid_response")
            start, end = _segment_bounds(
                utterance.get("start"), utterance.get("end"), duration_seconds
            )
            if speaker not in speaker_ids:
                speaker_ids[speaker] = f"SPEAKER_{len(speaker_ids):02d}"
            segments.append(
                {
                    "start": start,
                    "end": end,
                    "speaker": speaker_ids[speaker],
                    "text": text.strip(),
                }
            )
        segments.sort(key=lambda row: (row["start"], row["end"]))
        chronological_ids = {}
        for segment in segments:
            label = segment["speaker"]
            if label not in chronological_ids:
                chronological_ids[label] = f"SPEAKER_{len(chronological_ids):02d}"
            segment["speaker"] = chronological_ids[label]
        return {"segments": segments, "num_speakers": len(speaker_ids)}

    @staticmethod
    def _word_result(
        transcript: dict[str, Any], duration_seconds: float
    ) -> dict[str, Any]:
        text = transcript.get("text")
        words = transcript.get("words")
        if not isinstance(text, str) or not isinstance(words, list):
            raise AssemblyAIProcessingError("invalid_response")
        if not text.strip() and not words:
            return {"segments": [], "num_speakers": 0}
        if not text.strip() or not words:
            raise AssemblyAIProcessingError("invalid_response")

        bounds = []
        for word in words:
            if not isinstance(word, dict):
                raise AssemblyAIProcessingError("invalid_response")
            bounds.append(
                _segment_bounds(word.get("start"), word.get("end"), duration_seconds)
            )
        start = min(pair[0] for pair in bounds)
        end = max(pair[1] for pair in bounds)
        return {
            "segments": [
                {
                    "start": start,
                    "end": end,
                    "speaker": "SPEAKER_00",
                    "text": text.strip(),
                }
            ],
            "num_speakers": 1,
        }

    def get_metadata(self) -> dict[str, str]:
        return {
            "engine": "assemblyai",
            "model": "universal-2",
            "device": "cloud",
            "language": "pt",
        }

    def get_device(self) -> str:
        return "cloud"


def _segment_bounds(start_ms: Any, end_ms: Any, duration_seconds: float) -> tuple[float, float]:
    if (
        isinstance(start_ms, bool)
        or isinstance(end_ms, bool)
        or not isinstance(start_ms, (int, float))
        or not isinstance(end_ms, (int, float))
        or not math.isfinite(start_ms)
        or not math.isfinite(end_ms)
    ):
        raise AssemblyAIProcessingError("invalid_response")

    start = start_ms / 1000.0
    end = end_ms / 1000.0
    if start < 0 or end <= start or end > duration_seconds + _TIMESTAMP_TOLERANCE_SECONDS:
        raise AssemblyAIProcessingError("invalid_response")
    bounded_start = min(start, duration_seconds)
    bounded_end = min(end, duration_seconds)
    if bounded_end <= bounded_start:
        raise AssemblyAIProcessingError("invalid_response")
    return bounded_start, bounded_end


def _failure_code(exc: Exception) -> str:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code is None:
        status_code = getattr(exc, "status_code", None)
    if status_code in {401, 403}:
        return "credential"
    if status_code == 429:
        return "quota"
    if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
        return "timeout"
    if status_code is not None:
        return "unavailable"
    return "unavailable"


def _state_error_code(error: Any) -> str:
    if not isinstance(error, str):
        return "invalid_response"
    lowered = error.lower()
    if "quota" in lowered or "limit" in lowered or "credit" in lowered:
        return "quota"
    if "auth" in lowered or "api key" in lowered or "credential" in lowered:
        return "credential"
    return "unavailable"
