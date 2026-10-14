"""Exercise real HTTP → PostgreSQL → RQ → supervised Worker → Meeting → HTTP.

Only the dedicated isolated Compose is accepted. Never resubmit a failed upload.
Outputs contain metrics, not transcripts, names, tokens, paths or provider secrets.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time

from metrics import quality, dispersion
from pipeline_metrics import calculate, elapsed_between, hypothesis, require_isolated, utc_now


def checked(response):
    if not response.is_success:
        # Do not include response bodies/headers/URLs in errors.
        raise RuntimeError(f"Benchmark HTTP status {response.status_code}")
    return response.json()


def login(client):
    response = checked(client.post("/auth/login", json={
        "username": "benchmark", "password": os.environ["AUTH_ADMIN_PASSWORD"]}))
    client.headers["Authorization"] = "Bearer " + response["access_token"]
    return response["user"]["id"]


def ensure_beta(client, user_id):
    plan = checked(client.get("/account/plan"))
    if plan["beta"] is None:
        checked(client.post(f"/admin/accounts/{user_id}/beta", json={
            "capabilities": ["transcription.local"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}))
    elif plan["beta"]["capabilities"] != ["transcription.local"]:
        raise RuntimeError("Unexpected permissions in disposable benchmark account")


def observe_persistence(transcription_id):
    from src.database import SessionLocal
    from src.models import TranscriptionJob, TranscriptionReservation, UsageEvent
    from src.workers.config import get_redis_connection
    from rq.job import Job
    from rq.exceptions import NoSuchJobError

    with SessionLocal() as db:
        job = db.query(TranscriptionJob).filter_by(transcription_id=transcription_id).one()
        reservation = db.query(TranscriptionReservation).filter_by(transcription_id=transcription_id).one()
        events = db.query(UsageEvent).filter_by(resource_type="transcription", resource_id=transcription_id).all()
        # Immutable per-resource events, not another ledger or an aggregate of unequal units.
        metrics = [{"metric": e.metric, "unit": e.unit, "quantity": str(e.quantity) if e.quantity is not None else None,
                    "status": e.status, "provider": e.provider, "credential_source": e.credential_source}
                   for e in events]
        row = dict(database_status=job.status, reservation_state=reservation.state,
                   usage_attempt_count=sum(e.metric == "attempt" for e in events), ledger=metrics,
                   queue_seconds=elapsed_between(job.created_at, job.started_at))
    try:
        rq = Job.fetch(f"transcription_{transcription_id}", connection=get_redis_connection())
        status = rq.get_status(refresh=True)
        row["rq_status"] = getattr(status, "value", status)
    except NoSuchJobError:
        row["rq_status"] = "missing"
    return row


def run_one(args, sequence, authorization):
    import httpx
    with httpx.Client(base_url="http://api:2020", timeout=60,
                      headers={"Authorization": authorization}) as client:
        start = time.monotonic()
        with args.audio.open("rb") as audio:
            response = client.post("/transcriptions/jobs", files={"file": ("fixture" + args.audio.suffix.lower(), audio)},
                data={"transcription_model": "whisper", "use_diarization": str(args.diarization).lower()})
        upload_seconds = time.monotonic() - start
        if response.status_code != 202:
            return {"sequence": sequence, "status": "admission_rejected", "http_status": response.status_code,
                    "upload_seconds": upload_seconds, "wer": None, "cer": None}
        tid = response.json()["transcription_id"]
        deadline = time.monotonic() + args.timeout
        failures = 0
        while True:
            status = client.get(f"/transcriptions/jobs/{tid}/status")
            if status.status_code == 503:
                failures += 1
            else:
                body = checked(status)
                if body["job_status"] in {"completed", "failed"}:
                    break
            if time.monotonic() >= deadline:
                return {"sequence": sequence, "status": "observation_timeout", "transcription_id": tid,
                        "poll_503_count": failures, "wer": None, "cer": None}
            time.sleep(args.poll_interval)
        result = checked(client.get(f"/transcriptions/{tid}"))
        meeting_ready = False
        if result["status"] == "completed":
            checked(client.get(f"/meetings/{tid}/transcript"))
            meeting_ready = True
        end_to_end_seconds = time.monotonic() - start
        # RQ finished status and finally-block telemetry can follow DB completion.
        for _ in range(50):
            durable = observe_persistence(tid)
            if durable["rq_status"] in {"finished", "failed", "missing", "stopped", "canceled"}:
                break
            time.sleep(0.1)
        evidence = Path("/evidence") / f"worker-{tid}.json"
        worker = json.loads(evidence.read_text()) if evidence.is_file() else {}
        score = quality(args.reference.read_text(encoding="utf-8"), hypothesis(result["segments"])) if args.reference and result["status"] == "completed" else {"wer": None, "cer": None}
        queue_seconds = durable.pop("queue_seconds")
        row = dict(sequence=sequence, transcription_id=tid, status=result["status"],
                   meeting_ready=meeting_ready, poll_503_count=failures,
                   num_speakers=result.get("num_speakers"), segment_count=len(result.get("segments", [])),
                   **calculate(worker, upload_seconds=upload_seconds,
                               end_to_end_seconds=end_to_end_seconds, queue_seconds=queue_seconds),
                   **score, **durable)
        # Verify durable HTTP result after *only this terminal* RQ record is removed.
        if args.invalidate_terminal_rq:
            from rq.job import Job
            from src.workers.config import get_redis_connection
            if durable["rq_status"] not in {"finished", "failed"}:
                raise RuntimeError("Refusing to invalidate a live RQ record")
            Job.fetch(f"transcription_{tid}", connection=get_redis_connection()).delete()
            after = checked(client.get(f"/transcriptions/{tid}"))
            row["result_survives_rq_removal"] = after["segments"] == result["segments"] and after["status"] == result["status"]
        return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--reference", type=Path, help="Human-validated reference only; absent means unknown WER/CER")
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--concurrency", type=int, choices=(1, 2, 3), default=1,
                        help="Concurrent HTTP submissions; actual Worker count is recorded separately")
    parser.add_argument("--diarization", action="store_true")
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--invalidate-terminal-rq", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9-]{1,64}", args.fixture_id) or args.repetitions < 1 or args.timeout <= 0 or args.poll_interval <= 0:
        parser.error("Invalid benchmark options")
    if args.output.exists():
        parser.error("Output exists; choose a new cohort, do not overwrite evidence")
    from src.config import settings
    require_isolated(settings)
    import httpx
    from rq import Worker
    from src.workers.config import get_redis_connection
    with httpx.Client(base_url="http://api:2020", timeout=30) as client:
        user_id = login(client)
        ensure_beta(client, user_id)
        authorization = client.headers["Authorization"]
    workers = Worker.all(connection=get_redis_connection())
    cohort_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        rows = list(pool.map(lambda i: run_one(args, i, authorization), range(1, args.repetitions + 1)))
    elapsed = time.monotonic() - cohort_start
    numeric_fields = ("upload_seconds", "queue_seconds", "engine_initialization_seconds", "conversion_seconds",
                      "asr_seconds", "diarization_seconds", "persistence_seconds", "worker_seconds", "end_to_end_seconds",
                      "processing_rtf", "ram_peak_mib", "cpu_seconds", "wer", "cer")
    successful = [r for r in rows if r["status"] == "completed"]
    report = dict(schema_version=1, measured_at=utc_now(), environment="local_or_remote_must_be_declared_by_operator",
        fixture_id=args.fixture_id, diarization=args.diarization, submission_concurrency=args.concurrency,
        registered_workers=len(workers), repetitions=args.repetitions, wall_seconds=elapsed, rows=rows,
        summary={k: dispersion([r[k] for r in successful if r.get(k) is not None])
                 for k in numeric_fields if any(r.get(k) is not None for r in successful)},
        completed_audio_minutes_per_wall_hour=sum(r.get("audio_seconds") or 0 for r in successful) * 60 / elapsed,
        notes=["No VPS claim without real server hardware and billing evidence",
               "No resident-model warm mode: standard RQ forks and reloads every job",
               "Cohort throughput includes startup/upload/queue/poll; not a sustainable monthly capacity",
               "WER/CER absent without human reference; no DER without RTTM scoring",
               "Resource peaks are per work horse, not total stack or simultaneous cohort RAM"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
    print(json.dumps({"completed": len(successful), "observations": len(rows), "seconds": elapsed}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "harness_failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
