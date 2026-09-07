#!/usr/bin/env python
"""Run sequential jobs against one resident Faster-Whisper engine."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from benchmark_transcription import ResourceSampler, _git_state, _hardware, _sha256_file
from src import engine_registry
from src.services.faster_whisper_engine import FasterWhisperEngine
from src.services.transcription_processing_service import TranscriptionProcessingService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--language", default="pt")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be positive")

    load_started = time.perf_counter()
    engine = FasterWhisperEngine(
        model_name=args.model,
        device=args.device,
        compute_type=args.compute_type,
        language=args.language,
    )
    load_seconds = time.perf_counter() - load_started
    engine_registry.whisper_engine = engine
    service = TranscriptionProcessingService()
    model_identity = id(engine.model)
    runs = []

    for run_number in range(1, args.runs + 1):
        with ResourceSampler() as resources:
            started = time.perf_counter()
            result = service.process_transcription(
                file_path=args.audio,
                use_diarization=False,
                transcription_model="whisper",
            )
            elapsed = time.perf_counter() - started
        runs.append(
            {
                "run": run_number,
                "processing_seconds": round(elapsed, 6),
                "rtf": round(elapsed / result.duration_seconds, 6),
                "ram_start_mb": round(resources.ram_start / 1024**2, 2),
                "ram_end_mb": round(resources.ram_end / 1024**2, 2),
                "ram_peak_mb": round(resources.ram_peak / 1024**2, 2),
                "vram_start_mb": resources.vram_start,
                "vram_peak_mb": resources.vram_peak,
                "vram_measurement": resources.vram_measurement,
                "temporary_files": result.temporary_files,
                "temporary_bytes": result.temporary_bytes,
                "word_count": result.word_count,
                "model_reused": id(engine.model) == model_identity,
            }
        )

    output = {
        "schema_version": 1,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "source": _git_state(),
        "fixture": Path(args.audio).name,
        "fixture_sha256": _sha256_file(Path(args.audio)),
        "engine": engine.get_metadata(),
        "model_load_seconds": round(load_seconds, 6),
        "engine_instances": 1,
        "hardware": _hardware(),
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
