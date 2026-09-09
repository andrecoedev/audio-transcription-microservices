#!/usr/bin/env python
"""Calculate deterministic WER/CER against a human reference transcript."""

import argparse
import json
import re
import unicodedata
from pathlib import Path


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    return " ".join(re.findall(r"[^\W_]+(?:-[^\W_]+)*", text, flags=re.UNICODE))


def _distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for reference_item in reference:
        current = [previous[0] + 1]
        for index, hypothesis_item in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[index] + 1,
                    previous[index - 1] + (reference_item != hypothesis_item),
                )
            )
        previous = current
    return previous[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    reference = _normalize(args.reference.read_text(encoding="utf-8"))
    result = json.loads(args.result.read_text(encoding="utf-8"))
    hypothesis = _normalize(result["transcript"])
    reference_words = reference.split()
    hypothesis_words = hypothesis.split()
    reference_characters = list(reference.replace(" ", ""))
    hypothesis_characters = list(hypothesis.replace(" ", ""))
    output = {
        "fixture": result["fixture"],
        "fixture_sha256": result["fixture_sha256"],
        "engine": result["engine"],
        "reference_words": len(reference_words),
        "hypothesis_words": len(hypothesis_words),
        "word_errors": _distance(reference_words, hypothesis_words),
        "wer": round(_distance(reference_words, hypothesis_words) / len(reference_words), 6),
        "character_errors": _distance(reference_characters, hypothesis_characters),
        "cer": round(
            _distance(reference_characters, hypothesis_characters)
            / len(reference_characters),
            6,
        ),
    }
    serialized = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
