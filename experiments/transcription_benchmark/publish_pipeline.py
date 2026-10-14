"""Publish closed-field CSV of PUBLIC pipeline cohorts; private results stay local."""

import argparse
import csv
import json
from pathlib import Path


PUBLIC = frozenset({"fleurs-quality", "fleurs-six-minute", "fleurs-two-speaker"})
FIELDS = ("sequence", "status", "audio_seconds", "upload_seconds", "queue_seconds",
          "engine_initialization_seconds", "conversion_seconds", "asr_seconds", "diarization_seconds",
          "persistence_seconds", "worker_seconds", "end_to_end_seconds", "processing_rtf",
          "ram_peak_mib", "cpu_seconds", "temporary_bytes", "wer", "cer", "num_speakers",
          "segment_count", "segment_error_count", "usage_attempt_count", "reservation_state", "database_status",
          "rq_status", "result_survives_rq_removal")


def export_rows(reports):
    rows = []
    for cohort, report in enumerate(reports, 1):
        if report.get("fixture_id") not in PUBLIC:
            raise ValueError("Private/unknown fixture cannot be published")
        for raw in report["rows"]:
            row = {field: raw.get(field) for field in FIELDS}
            if "durable_admission_to_claim_seconds" not in raw:
                # Initial diagnostic cohort used DB admission→claim, not RQ queue.
                # Preserve other real measurements; never publish it as pure queue.
                row["queue_seconds"] = None
            row.update(cohort=cohort, fixture_id=report["fixture_id"], environment=report["environment"],
                       registered_workers=report["registered_workers"],
                       submission_concurrency=report["submission_concurrency"], diarization=report["diarization"],
                       measured_at=report["measured_at"])
            for field in ("cpu_threads", "beam_size", "compute_type", "device", "model", "decode_chunk_seconds",
                          "memory_limit_bytes", "cpu_quota_period"):
                row[field] = (report.get("runtime") or {}).get(field)
            rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--csv", required=True, type=Path)
    args = parser.parse_args()
    rows = export_rows([json.loads(file.read_text(encoding="utf-8")) for file in args.reports])
    if not rows:
        parser.error("No observations")
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("x", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Published {len(rows)} content-free public observations.")


if __name__ == "__main__":
    main()
