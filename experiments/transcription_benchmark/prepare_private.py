"""Prepare one bounded private-video excerpt locally; never prints its name.

Audio/hypotheses must remain ignored. No reference is fabricated. The longest
decodable file is selected by metadata, not by presumed content or quality.
"""

import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=600)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 3600:
        parser.error("Excerpt must be 1..3600 seconds")
    candidates = []
    for file in args.directory.glob("*.mp4"):
        completed = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                    "-of", "default=noprint_wrappers=1:nokey=1", str(file)],
                                   capture_output=True, text=True, timeout=30)
        if completed.returncode == 0:
            try:
                candidates.append((float(completed.stdout.strip()), file))
            except ValueError:
                pass
    if not candidates:
        raise SystemExit("No decodable MP4 metadata found")
    duration, selected = max(candidates, key=lambda item: item[0])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(selected),
                                "-t", str(args.seconds), "-vn", "-ac", "1", "-ar", "16000",
                                "-c:a", "pcm_s16le", str(args.output)], capture_output=True, timeout=300)
    if completed.returncode != 0:
        raise SystemExit("Cannot extract this video's audio; no filename or stderr disclosed")
    print(json.dumps({"fixture_id": "local-video-001", "duration_seconds": min(args.seconds, duration),
                      "reference_available": False, "upload_performed": False}))


if __name__ == "__main__":
    main()
