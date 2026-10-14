"""Generate PRIVATE configuration for a fresh benchmark, without reading any .env.

Run in a Python environment; no dependencies, network or provider credentials.
"""

import argparse
import os
from pathlib import Path
import secrets


def clean_path(path):
    result = path.resolve().as_posix()
    if any(c in result for c in ("\n", "\r", "'", "$")):
        raise ValueError("Unsupported configuration path")
    return "'" + result + "'"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True, help="Private ignored artifact directory")
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--api-image", required=True)
    parser.add_argument("--worker-image", required=True)
    args = parser.parse_args()
    if not (args.models / "faster-small" / "model.bin").is_file() or not args.fixtures.is_dir():
        parser.error("Provide existing authorized model cache and fixture directory")
    for value in (args.api_image, args.worker_image):
        if any(c.isspace() or c in "'$\"" for c in value):
            parser.error("Invalid image reference")
    args.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    evidence = args.directory / "evidence"
    evidence.mkdir(exist_ok=True, mode=0o700)
    target = args.directory / ".env.benchmark"
    values = dict(BENCHMARK_PROJECT="usagi-whisper-bench-" + secrets.token_hex(4),
                  BENCHMARK_DATABASE_PASSWORD=secrets.token_urlsafe(32),
                  BENCHMARK_JWT_SECRET=secrets.token_urlsafe(48),
                  BENCHMARK_LOGIN_PASSWORD=secrets.token_urlsafe(24),
                  BENCHMARK_MODELS=clean_path(args.models),
                  BENCHMARK_FIXTURES=clean_path(args.fixtures),
                  BENCHMARK_EVIDENCE=clean_path(evidence),
                  BENCHMARK_API_IMAGE=args.api_image,
                  BENCHMARK_WORKER_IMAGE=args.worker_image)
    # Exclusive creation and 0600 from first publication. Never overwrite an env.
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    print("Private benchmark configuration created; values intentionally not printed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Preparation failed (" + type(error).__name__ + "); no configuration disclosed.")
        raise SystemExit(1) from None
