"""Small, ML-free projection of the transcript already stored by Transcription."""

from __future__ import annotations


def ordered_segments(segments: list[dict] | None) -> list[dict]:
    """Return deterministic timeline order without duplicating persisted text."""
    indexed = list(enumerate(segments or []))
    indexed.sort(
        key=lambda item: (
            float(item[1]["start"]),
            float(item[1]["end"]),
            item[0],
        )
    )
    return [
        {
            **segment,
            "order": order,
            "start": float(segment["start"]),
            "end": float(segment["end"]),
        }
        for order, (_original_index, segment) in enumerate(indexed)
    ]


def speaker_ids(segments: list[dict]) -> list[str]:
    """Keep stable pipeline IDs in first-appearance order."""
    return list(
        dict.fromkeys(
            segment["speaker"]
            for segment in segments
            if isinstance(segment.get("speaker"), str) and segment["speaker"]
        )
    )
