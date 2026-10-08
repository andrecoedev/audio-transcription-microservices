"""Explicitly authorized model download only; never loads media or production.

Mount the existing backend .env read-only at --credential-file. Only HF_TOKEN
is consumed; no token is written to cache, console, image, or report. This does
not accept terms: it stops if the configured account lacks existing access.
"""

import argparse
import contextlib
import io
import json
import logging
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    from dotenv.parser import parse_stream
    with args.credential_file.open(encoding="utf-8") as stream:
        token = next((item.value for item in parse_stream(stream) if item.key == "HF_TOKEN"), None)
    if not token:
        raise SystemExit("HF token is not configured; no downloads attempted")
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from huggingface_hub import snapshot_download
            for model in ["pyannote/speaker-diarization-3.1", "pyannote/segmentation-3.0",
                          "pyannote/wespeaker-voxceleb-resnet34-LM"]:
                snapshot_download(model, token=token, cache_dir=str(args.cache),
                                  allow_patterns=["config.yaml", "config.json", "pytorch_model.bin"])
        print(json.dumps({"status": "downloaded", "models": 3, "token_saved": False}))
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
