"""Generate isolated non-speech fixtures for failures, NEVER quality evaluation."""

import argparse
from pathlib import Path
import wave


def prepare(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "invalid.wav").open("xb") as file:
        file.write(b"synthetic-not-an-audio-file")
    with (directory / "corrupt.wav").open("xb") as file:
        file.write(b"RIFF" + (100000).to_bytes(4, "little") + b"WAVE" + b"truncated")
    with (directory / "silence.wav").open("xb") as file:
        with wave.open(file, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\0\0" * 16000 * 20)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.directory)
    print("Three synthetic failure-only fixtures created; existing files are never overwritten.")
