#!/usr/bin/env python
"""Inspect raw Faster-Whisper metadata for selected diarization turns."""

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from src.services.faster_whisper_engine import FasterWhisperEngine
from src.utils.audio import decode_audio_segment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--segment", action="append", required=True, metavar="START:END")
    parser.add_argument("--language", default="auto")
    args = parser.parse_args()
    engine = FasterWhisperEngine(
        model_name="large-v3",
        device="cuda",
        compute_type="float16",
        language=args.language,
    )
    output = []
    for value in args.segment:
        start, end = (float(item) for item in value.split(":", 1))
        pcm = decode_audio_segment(args.audio, start=start, duration=end - start)
        segments, _ = engine.model.transcribe(
            pcm,
            language=None if args.language == "auto" else args.language,
            task="transcribe",
            beam_size=engine.beam_size,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=False,
        )
        output.append(
            {
                "source_start": start,
                "source_end": end,
                "duration": end - start,
                "segments": [
                    {
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text,
                        "average_log_probability": segment.avg_logprob,
                        "no_speech_probability": segment.no_speech_prob,
                    }
                    for segment in segments
                ],
            }
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
