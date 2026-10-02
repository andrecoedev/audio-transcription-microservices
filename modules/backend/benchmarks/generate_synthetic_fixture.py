#!/usr/bin/env python
"""Generate a tiny non-speech WAV for decoder/cleanup smoke tests only."""

import argparse
import math
import struct
import wave
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("benchmarks/fixtures/synthetic.wav"))
    parser.add_argument("--seconds", type=float, default=5.0)
    args = parser.parse_args()
    sample_rate = 16_000
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.output), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        for index in range(int(args.seconds * sample_rate)):
            second = index / sample_rate
            amplitude = 0 if second < 1 else int(4000 * math.sin(2 * math.pi * 440 * second))
            output.writeframesraw(struct.pack("<h", amplitude))
    print(args.output.resolve())


if __name__ == "__main__":
    main()
