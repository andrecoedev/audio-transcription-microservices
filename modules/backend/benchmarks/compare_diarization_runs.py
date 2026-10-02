"""Compare stored P1-C/P2-C diarization runs under one DER implementation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from benchmark_diarization_robustness import _load_reference, _score


def _production(mode: dict) -> dict:
    return next(
        item
        for item in mode["filter_experiments"]
        if item["name"] == "production_0.0s_-100dbfs"
    )


def compare(baseline_path: Path, candidate_path: Path, manifest_path: Path) -> dict:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if baseline["method"] != candidate["method"]:
        raise ValueError("Benchmark metric, collar or overlap policy changed")
    if (baseline["manifest"] != candidate["manifest"] or
            candidate["manifest"] != manifest_path.name):
        raise ValueError("Fixture manifests differ")

    rows = []
    for fixture_spec, old, new in zip(
        manifest["fixtures"], baseline["fixtures"], candidate["fixtures"], strict=True
    ):
        if fixture_spec["name"] != old["name"] or old["name"] != new["name"]:
            raise ValueError("Fixture order/name mismatch")
        if (old["reference"] != new["reference"] or
                new["reference"] != fixture_spec["reference"]):
            raise ValueError("Reference file mismatch")
        if (old["duration_seconds"] != new["duration_seconds"] or
                new["duration_seconds"] != fixture_spec["duration_seconds"]):
            raise ValueError("Duration limit mismatch")
        audio = manifest_path.parent / fixture_spec["audio"]
        if hashlib.sha256(audio.read_bytes()).hexdigest() != fixture_spec["sha256"]:
            raise ValueError(f"Audio hash changed: {fixture_spec['name']}")
        reference = _load_reference(manifest_path.parent / fixture_spec["reference"])
        duration = fixture_spec["duration_seconds"]
        for old_mode, new_mode in zip(old["modes"], new["modes"], strict=True):
            if old_mode["mode"] != new_mode["mode"]:
                raise ValueError("Mode mismatch")
            if old_mode["pipeline_options"] != new_mode["pipeline_options"]:
                raise ValueError("Pipeline options mismatch")
            old_filters = [
                (item["name"], item["minimum_segment_seconds"],
                 item["silence_threshold_dbfs"])
                for item in old_mode["filter_experiments"]
            ]
            new_filters = [
                (item["name"], item["minimum_segment_seconds"],
                 item["silence_threshold_dbfs"])
                for item in new_mode["filter_experiments"]
            ]
            if old_filters != new_filters:
                raise ValueError("Post-processing filter configuration changed")
            if not new_mode.get("adapter_preserved_all_tracks"):
                raise ValueError("Candidate adapter was not verified")
            if new_mode["adapter_segments"] != new_mode["native_segments"]:
                raise ValueError("Candidate adapter lost native segments")
            old_filter, new_filter = _production(old_mode), _production(new_mode)
            if new_mode["raw_segments"] != new_mode["native_segments"]:
                raise ValueError("Candidate benchmark dropped native segments")
            if (new_filter["segments"] != new_mode["raw_segments"] or
                    new_filter["speakers"] != new_mode["raw_speakers"]):
                raise ValueError("Candidate production filter dropped segments or speakers")
            old_der = _score(reference, old_filter["rows"], duration)["with_overlap"]
            new_der = _score(reference, new_filter["rows"], duration)["with_overlap"]
            rows.append(
                {
                    "fixture": old["name"],
                    "mode": old_mode["mode"],
                    "same_audio_sha256": True,
                    "same_pipeline_options": True,
                    "baseline_recorded_der": old_filter["metrics"]["with_overlap"]["der_percent"],
                    "baseline_rescored_der": old_der["der_percent"],
                    "candidate_recorded_der": new_filter["metrics"]["with_overlap"]["der_percent"],
                    "candidate_rescored_der": new_der["der_percent"],
                    "baseline_components": old_der,
                    "candidate_components": new_der,
                    "baseline_raw_segments": old_mode["raw_segments"],
                    "candidate_raw_segments": new_mode["raw_segments"],
                    "candidate_native_segments": new_mode["native_segments"],
                    "candidate_adapter_segments": new_mode["adapter_segments"],
                    "baseline_speakers": old_filter["num_speakers"],
                    "candidate_speakers": new_filter["num_speakers"],
                    "baseline_rtf": old_mode["rtf"],
                    "candidate_rtf": new_mode["rtf"],
                    "baseline_ram_peak_mb": old_mode["ram_peak_mb"],
                    "candidate_ram_peak_mb": new_mode["ram_peak_mb"],
                    "baseline_vram_start_mb": old_mode["vram_start_mb"],
                    "candidate_vram_start_mb": new_mode["vram_start_mb"],
                    "baseline_vram_peak_mb": old_mode["vram_peak_mb"],
                    "candidate_vram_peak_mb": new_mode["vram_peak_mb"],
                    "vram_measurements": [
                        old_mode["vram_measurement"], new_mode["vram_measurement"]
                    ],
                }
            )
    return {"same_method": True, "same_manifest": True, "comparisons": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = compare(arguments.baseline, arguments.candidate, arguments.manifest)
    if arguments.output:
        arguments.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    for row in result["comparisons"]:
        print(
            row["fixture"], row["mode"],
            f"DER {row['baseline_rescored_der']} -> {row['candidate_rescored_der']}",
            f"segments {row['baseline_raw_segments']} -> {row['candidate_raw_segments']}",
            f"adapter {row['candidate_adapter_segments']}/{row['candidate_native_segments']}",
        )
