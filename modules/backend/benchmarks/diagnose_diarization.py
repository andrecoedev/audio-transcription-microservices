#!/usr/bin/env python
"""Inspect Pyannote turns and compare post-filter configurations in one run."""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import librosa
import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from src.config import settings
from src.services.diarization_engine import DiarizationEngine


CONFIGURATIONS = (
    ("raw", 0.0, None),
    ("production-0.0s--100dbfs", 0.0, -100.0),
    ("legacy-0.5s--40dbfs", 0.5, -40.0),
    ("0.5s--30dbfs", 0.5, -30.0),
    ("0.3s--30dbfs", 0.3, -30.0),
    ("0.7s--35dbfs", 0.7, -35.0),
    ("0.5s--35dbfs", 0.5, -35.0),
    ("0.3s--35dbfs", 0.3, -35.0),
    ("0.5s--40dbfs", 0.5, -40.0),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _segment_dbfs(audio: np.ndarray, sample_rate: int, start: float, end: float) -> float:
    first = max(0, int(start * sample_rate))
    last = min(len(audio), int(end * sample_rate))
    samples = audio[first:last]
    if samples.size == 0:
        return -math.inf
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    return 20.0 * math.log10(rms) if rms > 0 else -math.inf


def _decision(duration: float, dbfs: float, minimum: float, threshold: float | None):
    if duration < minimum:
        return False, "duration"
    if threshold is not None and dbfs < threshold:
        return False, "volume"
    return True, None


def run(audio_path: Path) -> dict:
    if not settings.HF_TOKEN:
        raise RuntimeError("HF_TOKEN is required")

    engine = DiarizationEngine(settings.HF_TOKEN)
    audio, sample_rate = librosa.load(audio_path, sr=None, mono=True)
    audio_duration = len(audio) / sample_rate

    started = time.perf_counter()
    diarization = engine.pipeline(str(audio_path))
    pyannote_seconds = time.perf_counter() - started

    raw_rows = []
    for index, (turn, _, speaker) in enumerate(
        diarization.itertracks(yield_label=True), start=1
    ):
        start = max(0.0, float(turn.start))
        end = min(audio_duration, float(turn.end))
        duration = max(0.0, end - start)
        raw_rows.append(
            {
                "segment": index,
                "speaker": speaker,
                "start": round(start, 6),
                "end": round(end, 6),
                "duration": round(duration, 6),
                "dbfs": round(_segment_dbfs(audio, sample_rate, start, end), 3),
            }
        )

    experiments = []
    for name, minimum, threshold in CONFIGURATIONS:
        rows = []
        accepted_speakers = set()
        accepted_duration = 0.0
        rejection_counts = Counter()
        for raw in raw_rows:
            accepted, reason = _decision(
                raw["duration"], raw["dbfs"], minimum, threshold
            )
            row = dict(raw)
            row.update({"accepted": accepted, "rejection_reason": reason})
            rows.append(row)
            if accepted:
                accepted_speakers.add(raw["speaker"])
                accepted_duration += raw["duration"]
            else:
                rejection_counts[reason] += 1
        experiments.append(
            {
                "name": name,
                "minimum_segment_seconds": minimum,
                "silence_threshold_dbfs": threshold,
                "accepted_segments": sum(row["accepted"] for row in rows),
                "rejected_segments": len(rows) - sum(row["accepted"] for row in rows),
                "accepted_speakers": sorted(accepted_speakers),
                "num_speakers": len(accepted_speakers),
                "accepted_duration_seconds": round(accepted_duration, 6),
                "preserved_raw_duration_percent": round(
                    100 * accepted_duration / sum(row["duration"] for row in raw_rows), 3
                ) if raw_rows else 0.0,
                "rejections": dict(rejection_counts),
                "rows": rows,
            }
        )

    return {
        "schema_version": 1,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "fixture": audio_path.name,
        "fixture_sha256": _sha256(audio_path),
        "audio_duration_seconds": round(audio_duration, 6),
        "pyannote_seconds": round(pyannote_seconds, 6),
        "raw_segment_count": len(raw_rows),
        "raw_speakers": sorted({row["speaker"] for row in raw_rows}),
        "raw_speech_duration_seconds": round(
            sum(row["duration"] for row in raw_rows), 6
        ),
        "experiments": experiments,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.audio.resolve())
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "experiments"}, indent=2))
    print(json.dumps([
        {key: value for key, value in experiment.items() if key != "rows"}
        for experiment in result["experiments"]
    ], indent=2))


if __name__ == "__main__":
    main()
