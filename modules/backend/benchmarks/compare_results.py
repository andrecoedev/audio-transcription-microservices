#!/usr/bin/env python
"""Compare two benchmark JSON files produced on the same fixture/machine."""

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.lower(), flags=re.UNICODE))


def _percent_change(before: float | None, after: float | None) -> float | None:
    if before in (None, 0) or after is None:
        return None
    return round((after - before) / before * 100, 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    if before["fixture_sha256"] != after["fixture_sha256"]:
        raise SystemExit("Results use different audio fixtures")
    hardware_fields = (
        "os",
        "python",
        "cpu",
        "logical_cpu_count",
        "ram_total_mb",
        "gpus",
    )
    for field in hardware_fields:
        if before["hardware"].get(field) != after["hardware"].get(field):
            raise SystemExit(f"Results use different hardware/runtime field: {field}")
    for field in ("language", "diarization_enabled"):
        if before.get(field) != after.get(field):
            raise SystemExit(f"Results use different benchmark configuration: {field}")

    comparison = {
        "fixture": before["fixture"],
        "before_engine": before["engine"],
        "after_engine": after["engine"],
        "processing_change_percent": _percent_change(
            before["processing_seconds"], after["processing_seconds"]
        ),
        "rtf_change_percent": _percent_change(before["rtf"], after["rtf"]),
        "ram_peak_change_percent": _percent_change(
            before["ram_peak_mb"], after["ram_peak_mb"]
        ),
        "vram_peak_change_percent": _percent_change(
            before.get("vram_peak_delta_mb"), after.get("vram_peak_delta_mb")
        ),
        "temporary_files_change": (
            after["temporary_files"] - before["temporary_files"]
        ),
        "temporary_bytes_change": (
            after["temporary_bytes"] - before["temporary_bytes"]
        ),
        "word_count_change": after["word_count"] - before["word_count"],
        "segment_count_change": after["segment_count"] - before["segment_count"],
        "text_similarity": None,
    }
    if "transcript" in before and "transcript" in after:
        comparison["text_similarity"] = round(
            SequenceMatcher(
                None,
                _normalize(before["transcript"]),
                _normalize(after["transcript"]),
            ).ratio(),
            4,
        )
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
