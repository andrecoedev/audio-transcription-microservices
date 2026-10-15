"""Controlled faults on NEW synthetic jobs of the dedicated benchmark only.

Stop the benchmark Worker before prepare; start it afterwards, then inspect.
Never touches product containers/databases or changes application configuration.
"""

import argparse
import json
import re
from pathlib import Path

from pipeline_metrics import require_isolated
from run_pipeline import checked, ensure_beta, login, observe_persistence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("timeout", "missing-input", "inspect", "redis-unavailable"))
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--transcription-id", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; never resubmit an already prepared probe")
    from src.config import settings
    require_isolated(settings)
    import httpx
    if args.mode == "redis-unavailable":
        from src.database import SessionLocal
        from src.models import TranscriptionJob
        with SessionLocal() as db:
            before = db.query(TranscriptionJob).count()
        with httpx.Client(base_url="http://api:2020", timeout=10) as client:
            response = client.post("/transcriptions/jobs", files={"file": ("fixture.wav", b"synthetic")})
        with SessionLocal() as db:
            after = db.query(TranscriptionJob).count()
        if response.status_code != 503 or before != after:
            raise RuntimeError("Redis failure did not reject admission safely")
        with args.output.open("x", encoding="utf-8") as file:
            json.dump(dict(case=args.mode, http_status=503, jobs_unchanged=True), file)
        print(json.dumps({"case": args.mode, "http_status": 503, "jobs_unchanged": True}))
        return
    from rq import Worker
    from rq.job import Job
    from src.database import SessionLocal
    from src.models import TranscriptionJob, TranscriptionOwnership
    from src.services.audio_storage import get_audio_storage
    from src.workers.config import get_redis_connection, get_transcription_queue
    from src.workers.transcription_worker import recover_pending_jobs
    connection = get_redis_connection()
    with httpx.Client(base_url="http://api:2020", timeout=30) as client:
        user_id = login(client)
        if args.mode == "inspect":
            if args.transcription_id is None:
                parser.error("inspect requires the exact ID from a prepared probe")
            with SessionLocal() as db:
                db.query(TranscriptionOwnership).filter_by(transcription_id=args.transcription_id, user_id=user_id).one()
            row = observe_persistence(args.transcription_id)
            if row["database_status"] not in {"completed", "failed"}:
                raise RuntimeError("Probe still active; wait before reconciling")
            # Recovery must not repeat a terminal fault job or refund ambiguous work.
            recovered = recover_pending_jobs(get_transcription_queue(connection))
            after = observe_persistence(args.transcription_id)
            result = dict(case="inspect", recovered_jobs=recovered, before=row, after=after)
        else:
            if Worker.all(connection=connection):
                raise RuntimeError("Stop all benchmark Workers before preparing a fault")
            if args.audio is None:
                parser.error("preparation requires a public synthetic fixture")
            ensure_beta(client, user_id)
            with args.audio.open("rb") as file:
                created = checked(client.post("/transcriptions/jobs", files={"file": ("fixture.wav", file)},
                    data={"transcription_model": "whisper", "use_diarization": "false"}))
            tid = int(created["transcription_id"])
            # If a later fault mutation fails, this safe ID still permits manual
            # inspection. Do NOT repeat the POST to recover missing measurements.
            print(json.dumps({"status": "admitted", "transcription_id": tid}))
            with SessionLocal() as db:
                db.query(TranscriptionOwnership).filter_by(transcription_id=tid, user_id=user_id).one()
                job = db.query(TranscriptionJob).filter_by(transcription_id=tid, status="queued").one()
                rq_job = Job.fetch(f"transcription_{tid}", connection=connection)
                rq_status = rq_job.get_status(refresh=True)
                if getattr(rq_status, "value", rq_status) != "queued":
                    raise RuntimeError("Fault job was already claimed")
                if args.mode == "timeout":
                    # A per-job test override, not a weakened global timeout policy.
                    rq_job.timeout = 3
                    rq_job.save()
                    job.timeout_seconds = 3
                    db.commit()
                else:
                    get_audio_storage().delete(job.input_object_key)
            result = dict(case=args.mode, transcription_id=tid, status="prepared")
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
    print(json.dumps({"case": result["case"], "status": "recorded"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Only our closed diagnostic codes/HTTP status, never arbitrary exception text.
        reason = {"Stop all benchmark Workers before preparing a fault": "worker_registered",
                  "Fault job was already claimed": "job_claimed",
                  "Probe still active; wait before reconciling": "probe_active"}.get(str(error))
        http = re.fullmatch(r"Benchmark HTTP status (\d{3})", str(error))
        print(json.dumps({"status": "probe_failed", "error_type": type(error).__name__,
                          "reason": reason, "http_status": int(http.group(1)) if http else None}))
        raise SystemExit(1) from None
