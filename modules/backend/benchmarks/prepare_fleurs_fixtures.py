#!/usr/bin/env python
"""Build non-versioned PT-BR validation fixtures from public FLEURS audio."""

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydub import AudioSegment


@dataclass(frozen=True)
class Record:
    sentence_id: int
    filename: str
    raw_transcription: str
    normalized_transcription: str
    samples: int
    gender: str


def _read_tsv(path: Path) -> list[Record]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != 7:
            raise ValueError(f"Unexpected FLEURS row with {len(fields)} fields")
        records.append(
            Record(
                sentence_id=int(fields[0]),
                filename=fields[1],
                raw_transcription=fields[2],
                normalized_transcription=fields[3],
                samples=int(fields[5]),
                gender=fields[6],
            )
        )
    return records


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _first_unique(records: list[Record]) -> list[Record]:
    selected = []
    seen = set()
    for record in records:
        if record.sentence_id in seen:
            continue
        selected.append(record)
        seen.add(record.sentence_id)
    return selected


def _until_duration(
    records: list[Record],
    audio_directory: Path,
    target_seconds: float,
    pause_ms: int,
) -> list[Record]:
    selected = []
    duration_ms = 0
    for record in records:
        path = audio_directory / record.filename
        if not path.is_file():
            continue
        selected.append(record)
        duration_ms += len(AudioSegment.from_file(path))
        if len(selected) > 1:
            duration_ms += pause_ms
        if duration_ms >= target_seconds * 1000:
            break
    if duration_ms < target_seconds * 1000:
        raise RuntimeError(f"Only {duration_ms / 1000:.2f}s of audio was available")
    return selected


def _write_fixture(
    name: str,
    records: list[tuple[Record, Path]],
    output_directory: Path,
    pause_ms: int,
    fixture_type: str,
    expected_speakers: int | None,
) -> dict:
    combined = AudioSegment.empty()
    silence = AudioSegment.silent(duration=pause_ms, frame_rate=16_000)
    for index, (record, path) in enumerate(records):
        if index:
            combined += silence
        combined += AudioSegment.from_file(path).set_channels(1).set_frame_rate(16_000)

    audio_path = output_directory / f"{name}.wav"
    reference_path = output_directory / f"{name}.reference.txt"
    combined.export(audio_path, format="wav", parameters=["-acodec", "pcm_s16le"])
    reference_path.write_text(
        " ".join(record.raw_transcription for record, _ in records) + "\n",
        encoding="utf-8",
    )
    return {
        "name": name,
        "type": fixture_type,
        "audio": audio_path.name,
        "reference": reference_path.name,
        "duration_seconds": round(len(combined) / 1000, 3),
        "expected_speakers": expected_speakers,
        "pause_ms": pause_ms,
        "utterance_count": len(records),
        "sha256": _sha256(audio_path),
        "sources": [
            {
                "sentence_id": record.sentence_id,
                "filename": record.filename,
                "gender": record.gender,
                "source_sha256": _sha256(path),
            }
            for record, path in records
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-tsv", type=Path, required=True)
    parser.add_argument("--test-audio", type=Path, required=True)
    parser.add_argument("--train-tsv", type=Path, required=True)
    parser.add_argument("--female-audio", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)

    test_records = _first_unique(_read_tsv(args.test_tsv))
    train_records = _read_tsv(args.train_tsv)
    female_record = next(
        record
        for record in train_records
        if record.filename == "10037811280993524975.wav"
    )

    short_records = _until_duration(test_records, args.test_audio, 60.0, 250)
    long_records = _until_duration(test_records, args.test_audio, 360.0, 250)
    male_record = test_records[0]

    fixtures = [
        _write_fixture(
            "fleurs-ptbr-quality-1m",
            [(record, args.test_audio / record.filename) for record in short_records],
            args.output_directory,
            pause_ms=250,
            fixture_type="read_speech_quality",
            expected_speakers=None,
        ),
        _write_fixture(
            "fleurs-ptbr-representative-6m",
            [(record, args.test_audio / record.filename) for record in long_records],
            args.output_directory,
            pause_ms=250,
            fixture_type="read_speech_performance",
            expected_speakers=None,
        ),
        _write_fixture(
            "fleurs-ptbr-two-speaker-1m",
            [
                item
                for _ in range(4)
                for item in (
                    (male_record, args.test_audio / male_record.filename),
                    (female_record, args.female_audio),
                )
            ],
            args.output_directory,
            pause_ms=500,
            fixture_type="controlled_alternating_two_speaker",
            expected_speakers=2,
        ),
    ]
    manifest = {
        "dataset": "google/fleurs",
        "configuration": "pt_br",
        "license": "CC-BY-4.0",
        "source_revision": "70bb2e84b976b7e960aa89f1c648e09c59f894dd",
        "notes": (
            "FLEURS contains human-supervised read speech. The two-speaker fixture "
            "alternates two distinct source recordings and is not natural dialogue."
        ),
        "fixtures": fixtures,
    }
    manifest_path = args.output_directory / "fleurs-ptbr-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
