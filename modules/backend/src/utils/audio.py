"""Worker-only audio I/O built around bounded FFmpeg subprocesses."""

import json
import logging
import shutil
import subprocess
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)
SAMPLE_RATE = 16_000


class AudioProcessingError(RuntimeError):
    """Audio decoding or conversion failed."""


def _binary(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise AudioProcessingError(f"{name} was not found on PATH")
    return executable


def probe_audio_duration(input_path: str) -> float:
    """Read media duration without decoding the complete file."""
    command = [
        _binary("ffprobe"),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        input_path,
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        duration = float(json.loads(completed.stdout)["format"]["duration"])
    except (subprocess.CalledProcessError, KeyError, TypeError, ValueError) as exc:
        raise AudioProcessingError("Unable to determine audio duration") from exc
    if duration <= 0:
        raise AudioProcessingError("Audio duration must be greater than zero")
    return duration


def convert_to_wav(input_path: str, output_path: str, *, max_duration_seconds: int | None = None) -> tuple[str, float]:
    """Stream-decode media to one mono 16 kHz WAV used by the worker."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        _binary("ffmpeg"),
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-i",
        input_path,
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        str(destination),
    ]
    if max_duration_seconds is not None:
        # Decode only enough to reject overlong public uploads, even if their
        # compressed size is tiny or their duration metadata is misleading.
        command[-1:-1] = ["-t", str(max_duration_seconds + 1)]
    try:
        subprocess.run(command, check=True, capture_output=True)
        duration = probe_audio_duration(str(destination))
        return str(destination), duration
    except (OSError, subprocess.CalledProcessError, AudioProcessingError) as exc:
        destination.unlink(missing_ok=True)
        logger.error("Audio conversion failed (%s)", type(exc).__name__)
        raise AudioProcessingError("Unable to convert audio to WAV") from exc


def decode_audio_segment(
    input_path: str,
    start: float,
    duration: float,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Decode one bounded time window to normalized mono float32 PCM in memory."""
    if start < 0 or duration <= 0:
        raise ValueError("Audio window must have non-negative start and positive duration")
    command = [
        _binary("ffmpeg"),
        "-v",
        "error",
        "-nostdin",
        "-ss",
        f"{start:.6f}",
        "-t",
        f"{duration:.6f}",
        "-i",
        input_path,
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "-c:a",
        "pcm_s16le",
        "pipe:1",
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AudioProcessingError("Unable to decode audio segment") from exc

    pcm16 = np.frombuffer(completed.stdout, dtype=np.int16)
    if not pcm16.size:
        return np.empty(0, dtype=np.float32)
    return pcm16.astype(np.float32) / 32768.0
