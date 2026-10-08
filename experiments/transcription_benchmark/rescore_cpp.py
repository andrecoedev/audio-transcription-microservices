"""Rescore saved raw C++ segments without rerunning/changing measured inference."""

import argparse
import json
from pathlib import Path

from metrics import cpp_transcript, quality


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    reference = args.reference.read_text(encoding="utf-8")
    corrected = 0
    for file in args.results.glob(f"{args.fixture_id}-whisper.cpp-*.metrics.json"):
        rows = json.loads(file.read_text(encoding="utf-8"))
        for row in rows:
            hypothesis_path = file.with_name(file.name.replace(".metrics.json", f"-{row['repetition']}.hypothesis.json"))
            result = json.loads(hypothesis_path.read_text(encoding="utf-8"))
            row.update(quality(reference, cpp_transcript(result)))
            row["text_reconstruction"] = "native_segments_concat_no_display_newlines"
            corrected += 1
        file.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps({"rescored_rows": corrected, "inference_rerun": False,
                      "raw_hypotheses_preserved": True}))


if __name__ == "__main__":
    main()
