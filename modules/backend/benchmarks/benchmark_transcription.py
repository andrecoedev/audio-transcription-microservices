#!/usr/bin/env python
"""Reproducible worker-pipeline benchmark; does not involve the frontend/API."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from src import engine_registry
from src.config import settings
from src.services.transcription_processing_service import (
    TranscriptionProcessingService,
)


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _git_state() -> dict:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        return {"revision": revision, "dirty": bool(status.strip())}
    except (OSError, subprocess.SubprocessError):
        return {"revision": None, "dirty": None}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_nvidia_smi(*fields: str) -> list[str]:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={','.join(fields)}",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        return []


def _reported_cuda_version() -> str | None:
    try:
        completed = subprocess.run(
            ["nvidia-smi"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"CUDA(?: UMD)? Version:\s*([\d.]+)", completed.stdout)
    return match.group(1) if match else None


def _process_vram_mb(pid: int) -> float | None:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    total = 0.0
    found = False
    for line in completed.stdout.splitlines():
        columns = [column.strip() for column in line.split(",")]
        if len(columns) != 2 or columns[0] != str(pid):
            continue
        match = re.search(r"[\d.]+", columns[1])
        if match:
            total += float(match.group())
            found = True
    return total if found else None


class ResourceSampler:
    def __init__(self, interval: float = 0.05):
        self.interval = interval
        self.process = psutil.Process()
        self.ram_start = self.process.memory_info().rss
        self.ram_peak = self.ram_start
        self.vram_start = _process_vram_mb(self.process.pid)
        self.vram_peak = self.vram_start
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_args):
        self._stop.set()
        self._thread.join(timeout=2)
        self.ram_end = self.process.memory_info().rss
        self.ram_peak = max(self.ram_peak, self.ram_end)

    def _sample(self):
        while not self._stop.wait(self.interval):
            self.ram_peak = max(self.ram_peak, self.process.memory_info().rss)
            vram = _process_vram_mb(self.process.pid)
            if vram is not None:
                self.vram_peak = max(self.vram_peak or 0.0, vram)


class TemporaryFileSampler:
    def __init__(self, roots: list[Path], interval: float = 0.02):
        self.roots = roots
        self.interval = interval
        self.baseline = self._snapshot()
        self.maximum_sizes: dict[Path, int] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_args):
        self._sample_once()
        self._stop.set()
        self._thread.join(timeout=2)

    def _snapshot(self) -> set[Path]:
        return {
            path.resolve()
            for root in self.roots
            if root.exists()
            for path in root.rglob("*")
            if path.is_file()
        }

    def _sample_once(self):
        for root in self.roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.resolve() in self.baseline:
                    continue
                try:
                    self.maximum_sizes[path.resolve()] = max(
                        self.maximum_sizes.get(path.resolve(), 0),
                        path.stat().st_size,
                    )
                except OSError:
                    pass

    def _sample(self):
        while not self._stop.wait(self.interval):
            self._sample_once()


def _create_whisper_engine(args):
    if args.engine == "faster-whisper":
        from src.services.faster_whisper_engine import FasterWhisperEngine

        return FasterWhisperEngine(
            settings.HF_TOKEN,
            model_name=args.model,
            device=args.device,
            compute_type=args.compute_type,
            language=args.language,
        )

    from src.services.transcription_engine import WhisperEngine

    settings.FORCE_CPU = args.device == "cpu"
    settings.WHISPER_DTYPE = (
        "auto" if args.compute_type == "auto" else args.compute_type
    )
    return WhisperEngine(
        settings.HF_TOKEN,
        model_name=args.legacy_model,
    )


def _hardware() -> dict:
    gpu_rows = _run_nvidia_smi("name", "memory.total", "driver_version")
    return {
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor() or os.getenv("PROCESSOR_IDENTIFIER") or "unknown",
        "logical_cpu_count": psutil.cpu_count(),
        "ram_total_mb": round(psutil.virtual_memory().total / 1024**2, 2),
        "gpus": gpu_rows,
        "cuda_version_reported_by_driver": _reported_cuda_version(),
        "packages": {
            name: _package_version(name)
            for name in (
                "faster-whisper",
                "ctranslate2",
                "torch",
                "transformers",
                "pyannote.audio",
            )
        },
    }


def run(args) -> dict:
    audio_path = Path(args.audio).resolve()
    if not audio_path.is_file():
        raise FileNotFoundError(audio_path)
    if args.diarization and not settings.HF_TOKEN:
        raise RuntimeError("HF_TOKEN is required for a diarization benchmark")

    temp_root = BACKEND_ROOT / "temp"
    with ResourceSampler() as resources, TemporaryFileSampler([temp_root]) as temp:
        model_started = time.perf_counter()
        whisper_engine = _create_whisper_engine(args)
        model_load_seconds = time.perf_counter() - model_started
        engine_registry.whisper_engine = whisper_engine

        if args.diarization:
            from src.services.diarization_engine import DiarizationEngine

            engine_registry.diarization_engine = DiarizationEngine(settings.HF_TOKEN)

        processing_started = time.perf_counter()
        result = TranscriptionProcessingService().process_transcription(
            str(audio_path),
            use_diarization=args.diarization,
            transcription_model="whisper",
        )
        processing_seconds = time.perf_counter() - processing_started

    transcript = " ".join(segment["text"] for segment in result.segments).strip()
    temporary_files = max(len(temp.maximum_sizes), result.temporary_files)
    temporary_bytes = max(sum(temp.maximum_sizes.values()), result.temporary_bytes)
    metadata = getattr(whisper_engine, "get_metadata", lambda: {})()
    output = {
        "schema_version": 1,
        "measured_at": datetime.now(UTC).isoformat(),
        "source": _git_state(),
        "fixture": audio_path.name,
        "fixture_sha256": _sha256_file(audio_path),
        "engine": metadata.get("engine", "huggingface-whisper"),
        "model": metadata.get("model", args.legacy_model),
        "device": metadata.get("device", whisper_engine.get_device()),
        "compute_type": metadata.get("compute_type", settings.WHISPER_DTYPE),
        "language": metadata.get("language", args.language),
        "diarization_enabled": args.diarization,
        "audio_duration_seconds": round(result.duration_seconds, 6),
        "model_load_seconds": round(model_load_seconds, 6),
        "processing_seconds": round(processing_seconds, 6),
        "conversion_seconds": round(result.conversion_seconds, 6),
        "diarization_seconds": round(result.diarization_seconds, 6),
        "transcription_seconds": round(result.transcription_seconds, 6),
        "rtf": round(processing_seconds / result.duration_seconds, 6),
        "ram_start_mb": round(resources.ram_start / 1024**2, 2),
        "ram_end_mb": round(resources.ram_end / 1024**2, 2),
        "ram_peak_mb": round(resources.ram_peak / 1024**2, 2),
        "ram_peak_delta_mb": round(
            (resources.ram_peak - resources.ram_start) / 1024**2,
            2,
        ),
        "vram_start_mb": resources.vram_start,
        "vram_peak_mb": resources.vram_peak,
        "temporary_files": temporary_files,
        "temporary_bytes": temporary_bytes,
        "segment_count": len(result.segments),
        "word_count": result.word_count,
        "timestamps": [
            {
                "start": segment["start"],
                "end": segment["end"],
                "speaker": segment["speaker"],
            }
            for segment in result.segments
        ],
        "transcript_sha256": hashlib.sha256(transcript.encode()).hexdigest(),
        "hardware": _hardware(),
    }
    if args.include_text:
        output["transcript"] = transcript
    return output


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument(
        "--engine",
        choices=("huggingface", "faster-whisper"),
        required=True,
    )
    parser.add_argument("--model", default=settings.WHISPER_MODEL)
    parser.add_argument("--legacy-model", default="openai/whisper-large-v3")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--compute-type", default="auto")
    parser.add_argument("--language", choices=("pt", "en", "auto"), default="pt")
    parser.add_argument("--diarization", action="store_true")
    parser.add_argument("--include-text", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    result = run(args)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
