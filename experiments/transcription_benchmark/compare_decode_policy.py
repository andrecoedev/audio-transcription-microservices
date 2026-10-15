"""One paired public-fixture diagnostic; NOT a statistically repeated benchmark.

No product settings changed. Helps separate model quality from decode policy.
Never outputs hypotheses; never uses hypothesis as reference.
"""

import argparse
import json
import os
from pathlib import Path
import time

from metrics import quality


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if os.environ.get("HF_HUB_OFFLINE") != "1":
        parser.error("Only explicitly offline execution is accepted")
    from faster_whisper import WhisperModel
    from src.utils.audio import decode_audio_segment, probe_audio_duration
    from src.services.faster_whisper_engine import FasterWhisperEngine
    duration = probe_audio_duration(str(args.audio))
    pcm = decode_audio_segment(str(args.audio), start=0, duration=duration)
    reference = args.reference.read_text(encoding="utf-8")
    model = WhisperModel(str(args.model), device="cpu", compute_type="int8", cpu_threads=2, local_files_only=True)
    rows = []
    for tag, window_seconds, beam, language, previous in (
        ("product-policy", 300, 1, "pt", False),
        ("whole-audio-only", duration, 1, "pt", False),
        ("whole-audio-previous-text", duration, 1, "pt", True),
        ("historical-policy", duration, 5, None, True),
    ):
        texts = []
        started = time.monotonic()
        for sample in range(0, len(pcm), int(window_seconds * 16000)):
            window = pcm[sample:sample + int(window_seconds * 16000)]
            segments, info = model.transcribe(window, language=language, beam_size=beam, best_of=5,
                vad_filter=False, condition_on_previous_text=previous, temperature=0.0, word_timestamps=False)
            texts.extend(FasterWhisperEngine._consume_segments(segments, len(window) / 16000))
        score = quality(reference, " ".join(texts))
        rows.append(dict(policy=tag, window_seconds=window_seconds, beam_size=beam,
                         language=language or "auto", detected_language=info.language,
                         condition_on_previous_text=previous, inference_seconds=time.monotonic() - started,
                         repetitions=1, **score))
    with args.output.open("x", encoding="utf-8") as file:
        json.dump({"scope": "paired_diagnostic_not_capacity", "rows": rows}, file, indent=2)
    print(json.dumps({"diagnostic_policies": len(rows)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "diagnostic_failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
