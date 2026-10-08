"""Offline Pyannote 3.1 benchmark, separate from transcription quality."""

import argparse
import contextlib
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import time

from run import Sampler, decode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--reference-rttm", type=Path)
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], required=True)
    parser.add_argument("--session", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--num-speakers", type=int)
    args = parser.parse_args()
    # Must not fetch gated models or implicitly use cached authentication.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    # All Pyannote submodels must resolve the same explicitly mounted cache.
    os.environ["PYANNOTE_CACHE"] = "/models/pyannote"
    args.output.mkdir(parents=True, exist_ok=True)
    import torch
    torch_cache = Path(os.environ["PYANNOTE_CACHE"])
    revisions = {}
    for name in ("speaker-diarization-3.1", "segmentation-3.0", "wespeaker-voxceleb-resnet34-LM"):
        ref = torch_cache / f"models--pyannote--{name}" / "refs/main"
        revisions[name] = ref.read_text().strip() if ref.is_file() else None
    from pyannote.audio import Pipeline
    from pyannote.database.util import load_rttm
    from pyannote.metrics.diarization import DiarizationErrorRate
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; refusing CPU fallback")
    torch.set_num_threads(args.threads)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        audio = Path(temp) / "fixture.wav"
        duration, conversion = decode(args.audio, audio)
        with Sampler() as sampler:
            started = time.perf_counter()
            pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=False)
            if pipeline is None:
                raise RuntimeError("Authorized cached pipeline unavailable offline")
            pipeline.to(torch.device(args.device))
            load = time.perf_counter() - started
            if str(pipeline.device).split(":")[0] != args.device:
                raise RuntimeError("Unexpected actual device")
            rows = []
            for repetition in range(2):
                if args.device == "cuda":
                    torch.cuda.synchronize()
                    torch.cuda.reset_peak_memory_stats()
                started = time.perf_counter()
                options = {"num_speakers": args.num_speakers} if args.num_speakers else {}
                annotation = pipeline(str(audio), **options)
                if args.device == "cuda":
                    torch.cuda.synchronize()
                elapsed = time.perf_counter() - started
                score = None
                if args.reference_rttm:
                    references = load_rttm(str(args.reference_rttm))
                    if len(references) != 1:
                        raise ValueError("Exactly one matching fixture RTTM required")
                    score = float(DiarizationErrorRate(collar=0.25, skip_overlap=False)(
                        next(iter(references.values())), annotation))
                rows.append({"engine": "pyannote", "model": "speaker-diarization-3.1",
                             "fixture_id": args.fixture_id, "actual_device": args.device,
                             "session": args.session, "phase": "cold" if repetition == 0 else "warm",
                             "status": "completed", "audio_seconds": duration,
                             "model_load_seconds": load, "conversion_seconds": conversion,
                             "inference_seconds": elapsed, "rtf": elapsed / duration,
                             "speaker_count": len(annotation.labels()),
                             "segment_count": len(list(annotation.itertracks())),
                             "known_num_speakers": args.num_speakers,
                             "model_revisions": json.dumps(revisions, sort_keys=True),
                             "audio_sha256": hashlib.sha256(args.audio.read_bytes()).hexdigest(),
                             "der": score, "der_collar_seconds": 0.25, "der_skip_overlap": False,
                             "torch_peak_allocated_mib": torch.cuda.max_memory_allocated() / 2**20 if args.device == "cuda" else None})
        for row in rows:
            row.update(sampler.result())
        filename = f"{args.fixture_id}-pyannote-{args.device}-{args.session}.metrics.json"
        (args.output / filename).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(json.dumps({"fixture_id": args.fixture_id, "device": args.device,
                          "session": args.session, "seconds": [r["inference_seconds"] for r in rows],
                          "der": [r["der"] for r in rows]}))


if __name__ == "__main__":
    try:
        # Third-party loader warnings/errors may contain paths; keep console safe.
        logging.disable(logging.CRITICAL)
        with contextlib.redirect_stderr(io.StringIO()):
            main()
    except Exception as error:
        print(json.dumps({"engine": "pyannote", "status": "failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
