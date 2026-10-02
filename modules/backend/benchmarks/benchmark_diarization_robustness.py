#!/usr/bin/env python
"""Run the P1-C real-audio diarization matrix outside the fast test suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import librosa
import numpy as np
import torch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from benchmark_transcription import ResourceSampler, _git_state, _hardware
from pyannote.core import Annotation, Segment, Timeline
from pyannote.metrics.diarization import DiarizationErrorRate
from src.config import settings
from src.services.diarization_engine import DiarizationEngine
from src.services.diarization_compat import speaker_turns


FILTERS = (
    ("raw", 0.0, None),
    ("legacy_0.5s_-40dbfs", 0.5, -40.0),
    ("production_0.0s_-100dbfs", 0.0, -100.0),
    ("candidate_0.3s_-40dbfs", 0.3, -40.0),
    ("candidate_0.3s_-50dbfs", 0.3, -50.0),
    ("candidate_0.0s_-50dbfs", 0.0, -50.0),
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_reference(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _annotation(rows: list[dict], uri: str) -> Annotation:
    annotation = Annotation(uri=uri)
    for index, row in enumerate(rows):
        start, end = float(row["start"]), float(row["end"])
        if end > start:
            annotation[Segment(start, end), index] = str(row["speaker"])
    return annotation


def _score(reference: list[dict], hypothesis: list[dict], duration: float) -> dict:
    ref = _annotation(reference, "reference")
    hyp = _annotation(hypothesis, "hypothesis")
    uem = Timeline([Segment(0.0, duration)], uri="fixture")

    def compute(skip_overlap: bool) -> dict:
        metric = DiarizationErrorRate(collar=0.25, skip_overlap=skip_overlap)
        components = metric.compute_components(ref, hyp, uem=uem)
        total = float(components["total"])
        result = {
            "der_percent": round(100.0 * metric.compute_metric(components), 3),
            "speaker_confusion_percent": round(
                100.0 * float(components["confusion"]) / total, 3
            ) if total else 0.0,
            "missed_speech_percent": round(
                100.0 * float(components["missed detection"]) / total, 3
            ) if total else 0.0,
            "false_alarm_percent": round(
                100.0 * float(components["false alarm"]) / total, 3
            ) if total else 0.0,
            "reference_speaker_seconds": round(total, 3),
        }
        result["speech_preserved_percent"] = round(
            100.0 - result["missed_speech_percent"], 3
        )
        return result

    return {
        "collar_seconds": 0.25,
        "overlap_policy": "included",
        "with_overlap": compute(False),
        "without_overlap": compute(True),
    }


def _segment_dbfs(audio: np.ndarray, rate: int, start: float, end: float) -> float:
    first = max(0, round(start * rate))
    last = min(len(audio), round(end * rate))
    samples = audio[first:last]
    if not samples.size:
        return -math.inf
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    return 20.0 * math.log10(rms) if rms > 0 else -math.inf


def _raw_rows(diarization, audio: np.ndarray, rate: int, duration: float) -> list[dict]:
    diarization = getattr(diarization, "speaker_diarization", diarization)
    rows = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        start = max(0.0, float(turn.start))
        end = min(duration, float(turn.end))
        if end <= start:
            continue
        rows.append(
            {
                "start": round(start, 6),
                "end": round(end, 6),
                "duration": round(end - start, 6),
                "speaker": str(speaker),
                "dbfs": round(_segment_dbfs(audio, rate, start, end), 3),
            }
        )
    return sorted(rows, key=lambda row: (row["start"], row["end"], row["speaker"]))


def _filter(rows: list[dict], minimum: float, threshold: float | None) -> list[dict]:
    return [
        row
        for row in rows
        if row["duration"] >= minimum
        and (threshold is None or row["dbfs"] >= threshold)
    ]


def _union_duration(rows: list[dict], *, only_overlap: bool = False) -> float:
    boundaries = sorted({value for row in rows for value in (row["start"], row["end"])})
    total = 0.0
    for first, last in zip(boundaries, boundaries[1:]):
        active = sum(row["start"] < last and row["end"] > first for row in rows)
        if active >= (2 if only_overlap else 1):
            total += last - first
    return total


def _intersection_with_union(start: float, end: float, rows: list[dict]) -> float:
    spans = sorted(
        (max(start, row["start"]), min(end, row["end"]))
        for row in rows
        if row["end"] > start and row["start"] < end
    )
    total = 0.0
    cursor = start
    for first, last in spans:
        first = max(cursor, first)
        if last > first:
            total += last - first
            cursor = last
    return total


def _short_speech_coverage(reference: list[dict], hypothesis: list[dict]) -> dict:
    short = [row for row in reference if float(row["end"]) - float(row["start"]) < 0.5]
    total = sum(float(row["end"]) - float(row["start"]) for row in short)
    covered = sum(
        _intersection_with_union(float(row["start"]), float(row["end"]), hypothesis)
        for row in short
    )
    return {
        "reference_turns_under_0_5s": len(short),
        "reference_short_speech_seconds": round(total, 3),
        "covered_short_speech_seconds": round(covered, 3),
        "short_speech_coverage_percent": round(100.0 * covered / total, 3)
        if total
        else None,
    }


def _evaluate_filters(reference: list[dict], raw: list[dict], duration: float) -> list[dict]:
    raw_speaker_time = sum(row["duration"] for row in raw)
    experiments = []
    for name, minimum, threshold in FILTERS:
        rows = _filter(raw, minimum, threshold)
        retained = sum(row["duration"] for row in rows)
        experiments.append(
            {
                "name": name,
                "minimum_segment_seconds": minimum,
                "silence_threshold_dbfs": threshold,
                "segments": len(rows),
                "speakers": sorted({row["speaker"] for row in rows}),
                "num_speakers": len({row["speaker"] for row in rows}),
                "retained_raw_speaker_time_percent": round(
                    100.0 * retained / raw_speaker_time, 3
                ) if raw_speaker_time else 0.0,
                "rejected_by_duration": sum(row["duration"] < minimum for row in raw),
                "rejected_by_volume_after_duration": sum(
                    row["duration"] >= minimum
                    and threshold is not None
                    and row["dbfs"] < threshold
                    for row in raw
                ),
                "hypothesis_overlap_seconds": round(
                    _union_duration(rows, only_overlap=True), 3
                ),
                "short_speech": _short_speech_coverage(reference, rows),
                "metrics": _score(reference, rows, duration),
                "rows": rows,
            }
        )
    return experiments


def _transcribe(engine, audio_path: Path, rows: list[dict]) -> tuple[list[dict], float]:
    started = time.perf_counter()
    output = []
    for row in rows:
        try:
            text = engine.transcribe_segment(
                str(audio_path), start=row["start"], end=row["end"]
            )
            output.append(
                {**row, "text": text, "text_sha256": _sha256_text(text), "error": None}
            )
        except Exception as exc:
            output.append(
                {
                    **row,
                    "text": "",
                    "text_sha256": _sha256_text(""),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return output, time.perf_counter() - started


def _classification(result: dict, expected_speakers: int) -> str:
    metrics = result["metrics"]["with_overlap"]
    correct_count = result["num_speakers"] == expected_speakers
    if (
        metrics["der_percent"] <= 25.0
        and metrics["speech_preserved_percent"] >= 95.0
        and correct_count
    ):
        return "APROVADO"
    if metrics["der_percent"] <= 40.0 and metrics["speech_preserved_percent"] >= 85.0:
        return "ACEITÁVEL COM LIMITAÇÕES"
    return "REPROVADO"


def run(args) -> dict:
    manifest_path = args.manifest.resolve()
    fixture_root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not settings.HF_TOKEN:
        raise RuntimeError("HF_TOKEN is required for real Pyannote evaluation")

    with ResourceSampler(interval=0.1) as global_resources:
        load_started = time.perf_counter()
        diarization_engine = DiarizationEngine(settings.HF_TOKEN)
        diarization_load_seconds = time.perf_counter() - load_started
        pipeline_identity = id(diarization_engine.pipeline)

        whisper_engine = None
        whisper_load_seconds = 0.0
        if args.with_transcription:
            from src.services.faster_whisper_engine import FasterWhisperEngine

            load_started = time.perf_counter()
            whisper_engine = FasterWhisperEngine(
                settings.HF_TOKEN,
                model_name=args.model,
                device=args.device,
                compute_type=args.compute_type,
                language=manifest.get("language", "auto"),
            )
            whisper_load_seconds = time.perf_counter() - load_started

        fixtures = []
        for fixture in manifest["fixtures"]:
            audio_path = fixture_root / fixture["audio"]
            reference = _load_reference(fixture_root / fixture["reference"])
            audio, rate = librosa.load(audio_path, sr=None, mono=True)
            duration = len(audio) / rate
            expected = len({row["speaker"] for row in reference})
            modes = []
            for mode, pipeline_options in (
                ("automatic", {}),
                ("known_num_speakers", {"num_speakers": expected}),
            ):
                if torch.cuda.is_available():
                    torch.cuda.reset_peak_memory_stats()
                with ResourceSampler(interval=0.05) as resources:
                    started = time.perf_counter()
                    diarization = diarization_engine.pipeline(
                        str(audio_path), **pipeline_options
                    )
                    diarization_seconds = time.perf_counter() - started
                    annotation = getattr(diarization, "speaker_diarization", diarization)
                    native_turns = sorted(
                        (float(turn.start), float(turn.end), str(speaker))
                        for turn, _, speaker in annotation.itertracks(yield_label=True)
                    )
                    adapted_turns = sorted(
                        (float(turn.start), float(turn.end), str(speaker))
                        for turn, speaker in speaker_turns(diarization)
                    )
                    if adapted_turns != native_turns:
                        raise RuntimeError("Pyannote output adapter changed diarization tracks")
                    raw = _raw_rows(diarization, audio, rate, duration)
                    experiments = _evaluate_filters(reference, raw, duration)
                    current = next(
                        item
                        for item in experiments
                        if item["name"] == "production_0.0s_-100dbfs"
                    )
                    transcript_rows = []
                    transcription_seconds = 0.0
                    if whisper_engine is not None and mode == "automatic":
                        transcript_rows, transcription_seconds = _transcribe(
                            whisper_engine, audio_path, current["rows"]
                        )
                modes.append(
                    {
                        "mode": mode,
                        "pipeline_options": pipeline_options,
                        "diarization_seconds": round(diarization_seconds, 6),
                        "transcription_seconds": round(transcription_seconds, 6),
                        "total_processing_seconds": round(
                            diarization_seconds + transcription_seconds, 6
                        ),
                        "rtf": round(
                            (diarization_seconds + transcription_seconds) / duration, 6
                        ),
                        "ram_start_mb": round(resources.ram_start / 1024**2, 2),
                        "ram_end_mb": round(resources.ram_end / 1024**2, 2),
                        "ram_peak_mb": round(resources.ram_peak / 1024**2, 2),
                        "vram_start_mb": resources.vram_start,
                        "vram_peak_mb": resources.vram_peak,
                        "vram_measurement": resources.vram_measurement,
                        "torch_cuda_peak_allocated_mb": (
                            round(torch.cuda.max_memory_allocated() / 1024**2, 2)
                            if torch.cuda.is_available() else None
                        ),
                        "torch_cuda_peak_reserved_mb": (
                            round(torch.cuda.max_memory_reserved() / 1024**2, 2)
                            if torch.cuda.is_available() else None
                        ),
                        "raw_segments": len(raw),
                        "native_segments": len(native_turns),
                        "adapter_segments": len(adapted_turns),
                        "adapter_preserved_all_tracks": True,
                        "raw_speakers": sorted({row["speaker"] for row in raw}),
                        "raw_overlap_seconds": round(
                            _union_duration(raw, only_overlap=True), 3
                        ),
                        "raw_dbfs": {
                            "minimum": min((row["dbfs"] for row in raw), default=None),
                            "maximum": max((row["dbfs"] for row in raw), default=None),
                            "median": round(
                                float(np.median([row["dbfs"] for row in raw])), 3
                            ) if raw else None,
                        },
                        "filter_experiments": experiments,
                        "classification_current": _classification(current, expected),
                        "transcript": transcript_rows,
                    }
                )
            fixtures.append(
                {
                    **fixture,
                    "expected_speakers": expected,
                    "reference_overlap_seconds": round(
                        _union_duration(reference, only_overlap=True), 3
                    ),
                    "reference_dbfs": {
                        "minimum": min(
                            (row["dbfs"] for row in reference if row["dbfs"] is not None),
                            default=None,
                        ),
                        "maximum": max(
                            (row["dbfs"] for row in reference if row["dbfs"] is not None),
                            default=None,
                        ),
                    },
                    "modes": modes,
                }
            )

    return {
        "schema_version": 1,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "source": _git_state(),
        "method": {
            "metric": "pyannote.metrics.diarization.DiarizationErrorRate",
            "collar_seconds": 0.25,
            "primary_overlap_policy": "included",
            "secondary_overlap_policy": "excluded",
            "quality_thresholds": {
                "approved": "DER <= 25%, speech preserved >= 95%, speaker count correct",
                "acceptable": "DER <= 40%, speech preserved >= 85%",
                "failed": "otherwise",
            },
        },
        "engines": {
            "pyannote_model": (
                "pyannote/speaker-diarization-community-1"
                if int(version("pyannote.audio").split(".", 1)[0]) >= 4
                else "pyannote/speaker-diarization-3.1"
            ),
            "pyannote_device": diarization_engine.get_device(),
            "pyannote_load_seconds": round(diarization_load_seconds, 6),
            "pyannote_pipeline_instances": 1,
            "pyannote_reused": id(diarization_engine.pipeline) == pipeline_identity,
            "whisper_load_seconds": round(whisper_load_seconds, 6),
            "whisper": (
                whisper_engine.get_metadata() if whisper_engine is not None else None
            ),
        },
        "global_resources": {
            "ram_start_mb": round(global_resources.ram_start / 1024**2, 2),
            "ram_end_mb": round(global_resources.ram_end / 1024**2, 2),
            "ram_peak_mb": round(global_resources.ram_peak / 1024**2, 2),
            "vram_start_mb": global_resources.vram_start,
            "vram_peak_mb": global_resources.vram_peak,
            "vram_measurement": global_resources.vram_measurement,
        },
        "hardware": _hardware(),
        "manifest": manifest_path.name,
        "fixtures": fixtures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--with-transcription", action="store_true")
    parser.add_argument("--model", default=settings.WHISPER_MODEL)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--compute-type", default="float16")
    args = parser.parse_args()
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = []
    for fixture in result["fixtures"]:
        for mode in fixture["modes"]:
            current = next(
                item
                for item in mode["filter_experiments"]
                if item["name"] == "production_0.0s_-100dbfs"
            )
            summary.append(
                {
                    "fixture": fixture["name"],
                    "mode": mode["mode"],
                    "expected_speakers": fixture["expected_speakers"],
                    "detected_speakers": current["num_speakers"],
                    **current["metrics"]["with_overlap"],
                    "classification": mode["classification_current"],
                    "diarization_seconds": mode["diarization_seconds"],
                    "transcription_seconds": mode["transcription_seconds"],
                }
            )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
