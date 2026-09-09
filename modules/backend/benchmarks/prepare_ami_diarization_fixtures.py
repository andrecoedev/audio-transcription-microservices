#!/usr/bin/env python
"""Build reproducible P1-C fixtures from public AMI meeting material.

Audio and generated references stay under the ignored fixtures directory.  The
source RTTM is the `only_words` reference from AMI-diarization-setup and is
derived from AMI's manual word annotations, not from Pyannote predictions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import wave
import xml.etree.ElementTree as ET
from array import array
from dataclasses import dataclass
from pathlib import Path


NITE_ID = "{http://nite.sourceforge.net/}id"


@dataclass(frozen=True)
class Turn:
    speaker: str
    start: float
    end: float
    text: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_rttm(path: Path) -> list[Turn]:
    turns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        columns = line.split()
        if not columns or columns[0] != "SPEAKER":
            continue
        start = float(columns[3])
        turns.append(Turn(columns[7], start, start + float(columns[4])))
    return turns


def speaker_agents(meetings_xml: Path, meeting: str) -> dict[str, str]:
    root = ET.parse(meetings_xml).getroot()
    for node in root:
        if node.attrib.get("observation") == meeting:
            return {
                child.attrib["global_name"]: child.attrib["nxt_agent"]
                for child in node
                if child.tag.endswith("speaker")
            }
    raise ValueError(f"Meeting {meeting!r} is absent from {meetings_xml}")


def parse_words(words_dir: Path, meeting: str, agents: dict[str, str]):
    result: dict[str, list[tuple[float, float, str]]] = {}
    for speaker, agent in agents.items():
        root = ET.parse(words_dir / f"{meeting}.{agent}.words.xml").getroot()
        words = []
        for node in root:
            if not node.tag.endswith("w"):
                continue
            try:
                start = float(node.attrib["starttime"])
                end = float(node.attrib["endtime"])
            except (KeyError, ValueError):
                continue
            text = (node.text or "").strip()
            if text:
                words.append((start, end, text))
        result[speaker] = words
    return result


def attach_text(turns: list[Turn], words: dict[str, list[tuple[float, float, str]]]):
    output = []
    for turn in turns:
        tokens = [
            text
            for start, end, text in words.get(turn.speaker, [])
            if end > turn.start and start < turn.end
        ]
        text = " ".join(tokens)
        text = re.sub(r"\s+([.,!?;:])", r"\1", text)
        output.append(Turn(turn.speaker, turn.start, turn.end, text))
    return output


def clip(turns: list[Turn], start: float, duration: float) -> list[Turn]:
    end = start + duration
    return [
        Turn(
            turn.speaker,
            max(turn.start, start) - start,
            min(turn.end, end) - start,
            turn.text,
        )
        for turn in turns
        if turn.end > start and turn.start < end
    ]


def timeline_stats(turns: list[Turn]) -> dict:
    boundaries = sorted({value for turn in turns for value in (turn.start, turn.end)})
    union = 0.0
    overlap = 0.0
    for first, last in zip(boundaries, boundaries[1:]):
        active = sum(turn.start < last and turn.end > first for turn in turns)
        if active:
            union += last - first
        if active > 1:
            overlap += last - first
    ordered = sorted(turns, key=lambda item: (item.start, item.end, item.speaker))
    speaker_seconds = {
        speaker: round(sum(turn.duration for turn in turns if turn.speaker == speaker), 3)
        for speaker in sorted({turn.speaker for turn in turns})
    }
    return {
        "speakers": sorted({turn.speaker for turn in turns}),
        "turns": len(turns),
        "short_turns_under_0_5s": sum(turn.duration < 0.5 for turn in turns),
        "speaker_switches": sum(
            first.speaker != second.speaker
            for first, second in zip(ordered, ordered[1:])
        ),
        "speech_union_seconds": round(union, 3),
        "overlap_seconds": round(overlap, 3),
        "speaker_seconds": speaker_seconds,
    }


def select_window(
    turns: list[Turn], duration: float, mode: str, meeting_duration: float
) -> tuple[float, dict]:
    candidates = []
    for second in range(0, max(1, math.floor(meeting_duration - duration) + 1), 5):
        rows = clip(turns, float(second), duration)
        stats = timeline_stats(rows)
        count = len(stats["speakers"])
        speech = stats["speech_union_seconds"]
        overlap = stats["overlap_seconds"]
        if mode == "clean":
            if (
                count != 2
                or speech < 18.0
                or overlap > 2.0
                or stats["turns"] < 6
                or min(stats["speaker_seconds"].values()) < 5.0
            ):
                continue
            score = speech - 8.0 * overlap
        elif mode == "rapid":
            if count < 2 or speech < 15.0:
                continue
            score = (
                stats["speaker_switches"]
                + 2.0 * stats["short_turns_under_0_5s"]
                + 0.1 * stats["turns"]
            )
        elif mode == "overlap":
            if count < 2:
                continue
            score = 10.0 * overlap + 0.05 * speech
        elif mode == "multi":
            if count < 4 or speech < 20.0:
                continue
            score = speech + 0.25 * stats["speaker_switches"]
        else:
            raise ValueError(mode)
        candidates.append((score, float(second), stats))
    if not candidates:
        raise RuntimeError(f"No valid {mode!r} window found")
    _, start, stats = max(candidates)
    return start, stats


def ffmpeg_cut(source: Path, target: Path, start: float, duration: float) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(start),
            "-t",
            str(duration),
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(target),
        ],
        check=True,
    )


def attenuate_speaker(source: Path, target: Path, turns: list[Turn], speaker: str):
    with wave.open(str(source), "rb") as reader:
        params = reader.getparams()
        if params.sampwidth != 2 or params.nchannels != 1:
            raise ValueError("Controlled attenuation requires mono PCM16")
        frames = array("h")
        frames.frombytes(reader.readframes(reader.getnframes()))
    factor = 10 ** (-18.0 / 20.0)
    intervals = [turn for turn in turns if turn.speaker == speaker]
    for turn in intervals:
        first = max(0, round(turn.start * params.framerate))
        last = min(len(frames), round(turn.end * params.framerate))
        for index in range(first, last):
            frames[index] = round(frames[index] * factor)
    with wave.open(str(target), "wb") as writer:
        writer.setparams(params)
        writer.writeframes(frames.tobytes())


def segment_dbfs(path: Path, start: float, end: float) -> float | None:
    with wave.open(str(path), "rb") as reader:
        rate = reader.getframerate()
        reader.setpos(min(reader.getnframes(), max(0, round(start * rate))))
        count = max(0, round((end - start) * rate))
        samples = array("h")
        samples.frombytes(reader.readframes(count))
    if not samples:
        return None
    mean_square = sum(sample * sample for sample in samples) / len(samples)
    if mean_square <= 0:
        return float("-inf")
    return 20.0 * math.log10(math.sqrt(mean_square) / 32768.0)


def write_reference(base: Path, turns: list[Turn], audio: Path) -> None:
    with base.with_suffix(".reference.jsonl").open("w", encoding="utf-8") as target:
        for turn in turns:
            target.write(
                json.dumps(
                    {
                        "speaker": turn.speaker,
                        "start": round(turn.start, 3),
                        "end": round(turn.end, 3),
                        "text": turn.text,
                        "dbfs": (
                            None
                            if (value := segment_dbfs(audio, turn.start, turn.end)) is None
                            else round(value, 3)
                        ),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    with base.with_suffix(".reference.rttm").open("w", encoding="utf-8") as target:
        for turn in turns:
            target.write(
                f"SPEAKER {base.name} 1 {turn.start:.3f} {turn.duration:.3f} "
                f"<NA> <NA> {turn.speaker} <NA> <NA>\n"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", default="ES2004a")
    parser.add_argument("--headset", type=Path, required=True)
    parser.add_argument("--far-field", type=Path, required=True)
    parser.add_argument("--rttm", type=Path, required=True)
    parser.add_argument("--manual-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    with wave.open(str(args.headset), "rb") as source:
        meeting_duration = source.getnframes() / source.getframerate()
    agents = speaker_agents(
        args.manual_root / "corpusResources" / "meetings.xml", args.meeting
    )
    turns = attach_text(
        parse_rttm(args.rttm),
        parse_words(args.manual_root / "words", args.meeting, agents),
    )
    selections = {
        "ami-clean-2spk": ("clean", 60.0, args.headset, "A"),
        "ami-rapid-turns": ("rapid", 60.0, args.headset, "C"),
        "ami-overlap": ("overlap", 60.0, args.headset, "D"),
        "ami-four-speakers": ("multi", 90.0, args.headset, "F"),
    }
    generated = []
    clean_start = None
    clean_turns = None
    source_windows = {}
    for name, (mode, duration, source, category) in selections.items():
        start, _ = select_window(turns, duration, mode, meeting_duration)
        rows = clip(turns, start, duration)
        audio = args.output_dir / f"{name}.wav"
        ffmpeg_cut(source, audio, start, duration)
        write_reference(args.output_dir / name, rows, audio)
        stats = timeline_stats(rows)
        generated.append(
            {
                "name": name,
                "category": category,
                "source_start_seconds": start,
                "duration_seconds": duration,
                "audio": audio.name,
                "reference": f"{name}.reference.jsonl",
                "source_type": "headset_mix",
                "controlled": False,
                "sha256": sha256(audio),
                **stats,
            }
        )
        if mode == "clean":
            clean_start, clean_turns = start, rows
        source_windows[mode] = start

    assert clean_start is not None and clean_turns is not None
    clean_speech = {
        speaker: sum(turn.duration for turn in clean_turns if turn.speaker == speaker)
        for speaker in {turn.speaker for turn in clean_turns}
    }
    quiet_speaker = min(clean_speech, key=clean_speech.get)
    unequal_audio = args.output_dir / "ami-unequal-volume-2spk.wav"
    attenuate_speaker(
        args.output_dir / "ami-clean-2spk.wav",
        unequal_audio,
        clean_turns,
        quiet_speaker,
    )
    write_reference(args.output_dir / "ami-unequal-volume-2spk", clean_turns, unequal_audio)
    generated.append(
        {
            "name": "ami-unequal-volume-2spk",
            "category": "B",
            "source_start_seconds": clean_start,
            "duration_seconds": 60.0,
            "audio": unequal_audio.name,
            "reference": "ami-unequal-volume-2spk.reference.jsonl",
            "source_type": "controlled_headset_mix",
            "controlled": True,
            "attenuated_speaker": quiet_speaker,
            "attenuation_db": -18.0,
            "sha256": sha256(unequal_audio),
            **timeline_stats(clean_turns),
        }
    )

    noise_start = source_windows["overlap"]
    noise_turns = clip(turns, noise_start, 60.0)
    noise_audio = args.output_dir / "ami-far-field-noise.wav"
    ffmpeg_cut(args.far_field, noise_audio, noise_start, 60.0)
    write_reference(args.output_dir / "ami-far-field-noise", noise_turns, noise_audio)
    generated.append(
        {
            "name": "ami-far-field-noise",
            "category": "E",
            "source_start_seconds": noise_start,
            "duration_seconds": 60.0,
            "audio": noise_audio.name,
            "reference": "ami-far-field-noise.reference.jsonl",
            "source_type": "array_microphone_1_channel_01",
            "controlled": False,
            "sha256": sha256(noise_audio),
            **timeline_stats(noise_turns),
        }
    )

    manifest = {
        "schema_version": 1,
        "dataset": "AMI Meeting Corpus",
        "meeting": args.meeting,
        "meeting_partition": "official Full-corpus-ASR test",
        "language": "en",
        "license": "CC BY 4.0",
        "reference_policy": "only_words RTTM derived from AMI manual annotations",
        "source_urls": {
            "headset": "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/HeadsetAudio/ES2004a.Mix-Headset.wav",
            "far_field": "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/ES2004a/audio/ES2004a.Array1-01.wav",
            "annotations": "https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip",
            "diarization_setup": "https://github.com/pyannote/AMI-diarization-setup",
        },
        "source_sha256": {
            "headset": sha256(args.headset),
            "far_field": sha256(args.far_field),
            "rttm": sha256(args.rttm),
        },
        "fixtures": sorted(generated, key=lambda item: item["category"]),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "p1c-ami-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
