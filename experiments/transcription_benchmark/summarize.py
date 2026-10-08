"""Export metadata-only CSV and medians; never export hypotheses or filenames."""

import argparse
import csv
import json
from pathlib import Path

from metrics import dispersion


def summarize(rows):
    groups = {}
    for row in rows:
        if row.get("status") != "completed":
            continue
        if row.get("requested_device", row["actual_device"]) != row["actual_device"]:
            raise ValueError("Device mismatch in benchmark evidence")
        key = tuple(row.get(field) for field in ("fixture_id", "engine", "model", "actual_device", "phase"))
        groups.setdefault(key, []).append(row)
    output = []
    for key, group in sorted(groups.items()):
        item = dict(zip(("fixture_id", "engine", "model", "device", "phase"), key))
        item["sessions"] = len({row["session"] for row in group})
        item["repeated_enough"] = item["sessions"] >= 3
        for field in ("audio_seconds", "model_load_seconds", "startup_seconds", "inference_seconds",
                      "total_seconds", "rtf", "wer", "cer", "der", "ram_peak_mib",
                      "gpu_total_vram_delta_mib", "gpu_percent_mean", "torch_peak_allocated_mib"):
            values = [row[field] for row in group if row.get(field) is not None]
            item[field] = dispersion(values) if values else None
        item["languages"] = sorted({row["language"] for row in group if row.get("language")})
        output.append(item)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for file in sorted(args.results.glob("*.metrics.json")):
        rows.extend(json.loads(file.read_text(encoding="utf-8")))
    if not rows:
        parser.error("No completed measurements")
    fields = sorted({key for row in rows for key in row})
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    args.summary.write_text(json.dumps(summarize(rows), indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "groups": len(summarize(rows))}))


if __name__ == "__main__":
    main()
