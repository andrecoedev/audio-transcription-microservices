"""Sample aggregate container resources of a dedicated benchmark project only.

Docker memory/CPU are not comparable to process RSS. Keep both scopes explicit.
Run beside the driver, not inside an API/Worker container. No Docker socket mount.
"""

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess
import time


def project_name(value):
    if not re.fullmatch(r"usagi-whisper-bench-[a-f0-9]{8}", value):
        raise ValueError("Only a generated isolated benchmark project is accepted")
    return value


def sample(project):
    project_name(project)
    ids = subprocess.run(["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={project}"],
                         check=True, capture_output=True, text=True, timeout=10).stdout.split()
    if not ids:
        raise RuntimeError("No running benchmark containers")
    result = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids],
                            check=False, capture_output=True, text=True, timeout=20)
    rows = []
    for line in result.stdout.splitlines():
        raw = json.loads(line)
        name = raw["Name"]
        if not name.startswith(project + "-"):
            raise RuntimeError("Unexpected resource scope")
        rows.append(dict(service=name[len(project) + 1:], cpu_percent=float(raw["CPUPerc"].rstrip("%")),
                         memory_usage=raw["MemUsage"], memory_percent=float(raw["MemPerc"].rstrip("%")),
                         pids=int(raw["PIDs"])))
    # A --rm driver may disappear between ps and stats. Retain valid samples;
    # never report a successful observation if Docker supplies none.
    if not rows:
        raise RuntimeError("No valid resource samples returned")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=project_name)
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--interval", type=float, default=2)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not 0 < args.seconds <= 7200 or args.interval < 1:
        parser.error("Require bounded duration (<=7200s) and interval >=1s")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=("elapsed_seconds", "service", "cpu_percent", "memory_usage", "memory_percent", "pids"))
        writer.writeheader()
        start = time.monotonic()
        while time.monotonic() - start < args.seconds:
            for row in sample(args.project):
                writer.writerow(dict(elapsed_seconds=time.monotonic() - start, **row))
            file.flush()
            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Resource sampling failed (" + type(error).__name__ + "); no command output disclosed.")
        raise SystemExit(1) from None
