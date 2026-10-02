"""Isolated synthetic RQ/PostgreSQL probe for CUDA, timeout and crash recovery.

Run only against an empty development database, never against production data.
The probe does not load transcription models or read audio; it exercises the
same durable job claim/persist/recovery functions as the real Worker.
"""

from __future__ import annotations

import argparse
import time
import uuid
from datetime import datetime, timezone

from rq import SimpleWorker, Worker
from rq.exceptions import NoSuchJobError
from rq.job import Job

from src.database import SessionLocal
from src.models import AuditEvent, Transcription, TranscriptionJob
from src.services.transcription_processing_service import ProcessingResult
from src.workers.config import get_redis_connection
from src.workers import transcription_worker

QUEUE_NAME = "p2c2_simpleworker_probe"
MARKER = "p2c2_simpleworker_probe_"


def _queue():
    from rq import Queue

    return Queue(QUEUE_NAME, connection=get_redis_connection())


def _get_record(db, label: str):
    return db.query(Transcription).filter(
        Transcription.original_filename == MARKER + label
    ).one_or_none()


def seed(label: str, timeout: int) -> None:
    db = SessionLocal()
    try:
        if _get_record(db, label):
            raise RuntimeError("Probe label already exists")
        transcription = Transcription(
            filename=MARKER + label,
            original_filename=MARKER + label,
            file_size_mb=0.0,
            duration_seconds=1.0,
            transcription_model="whisper",
            use_diarization=False,
            status="queued",
            segments=[],
        )
        db.add(transcription)
        db.flush()
        db.add(
            TranscriptionJob(
                transcription_id=transcription.id,
                input_path="/tmp/" + MARKER + label,
                use_diarization=False,
                transcription_model="whisper",
                status="queued",
            )
        )
        db.commit()
        _queue().enqueue(
            transcription_worker.process_transcription_job_sync,
            transcription.id,
            job_id=f"transcription_{transcription.id}",
            job_timeout=timeout,
        )
        print(f"seeded_id={transcription.id} timeout={timeout}")
    finally:
        db.close()


class SleepingCudaService:
    def __init__(self, seconds: float, label: str):
        self.seconds = seconds
        self.label = label

    def process_transcription(self, **_kwargs):
        get_redis_connection().incr(MARKER + self.label + "_attempts")
        time.sleep(self.seconds)
        return ProcessingResult(
            segments=[{"start": 0.0, "end": 1.0, "speaker": "speaker_0", "text": "probe"}],
            duration_seconds=1.0,
            num_speakers=1,
            word_count=1,
        )


def _cuda_service(label: str, seconds: float):
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for this operational probe")
    torch.cuda.init()
    get_redis_connection().incr(MARKER + label + "_cuda_initializations")
    print(f"child_cuda_initialized={torch.cuda.is_initialized()}", flush=True)
    return SleepingCudaService(seconds, label)


def work(label: str, seconds: float, fork: bool = False, automatic_recovery: bool = False) -> None:
    if fork:
        # The forked horse executes this function. The supervising parent has
        # not imported torch or initialized CUDA.
        import sys

        print(f"parent_torch_imported={'torch' in sys.modules}", flush=True)
        transcription_worker.get_processing_service = lambda: _cuda_service(label, seconds)
    else:
        transcription_worker._processing_service = _cuda_service(label, seconds)
    queue = _queue()
    recovered = transcription_worker.recover_pending_jobs(queue)
    print(f"recovered={recovered}", flush=True)
    if automatic_recovery:
        from run_worker import RecoveringWorker

        worker_type = RecoveringWorker
    else:
        worker_type = Worker if fork else SimpleWorker
    worker_options = {
        "default_worker_ttl": 75,
        "maintenance_interval": 60,
    } if automatic_recovery else {}
    worker = worker_type(
        [queue],
        connection=queue.connection,
        name="p2c2-probe-worker-" + uuid.uuid4().hex[:8],
        job_monitoring_interval=5,
        **worker_options,
    )
    worker.work(burst=not automatic_recovery, logging_level="WARNING", max_jobs=1)


def status(label: str) -> None:
    from rq import Worker

    db = SessionLocal()
    try:
        transcription = _get_record(db, label)
        if not transcription:
            raise RuntimeError("Probe label not found")
        queue = _queue()
        try:
            job = Job.fetch(f"transcription_{transcription.id}", connection=queue.connection)
            rq_status = job.get_status(refresh=True)
            rq_status = getattr(rq_status, "value", rq_status)
        except NoSuchJobError:
            rq_status = "missing"
        workers = Worker.all(connection=queue.connection)
        probe_workers = [
            worker for worker in workers if worker.name.startswith("p2c2-probe-worker-")
        ]
        heartbeat_age = None
        if probe_workers and probe_workers[0].last_heartbeat:
            heartbeat = probe_workers[0].last_heartbeat
            if heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=timezone.utc)
            heartbeat_age = round(
                (datetime.now(timezone.utc) - heartbeat).total_seconds(), 1
            )
        print(
            {
                "db_job_status": transcription.job.status,
                "db_transcription_status": transcription.status,
                "rq_status": rq_status,
                "started_registry": len(queue.started_job_registry),
                "failed_registry": len(queue.failed_job_registry),
                "worker_heartbeat_age_seconds": heartbeat_age,
                "attempts": int(queue.connection.get(MARKER + label + "_attempts") or 0),
                "cuda_initializations": int(queue.connection.get(MARKER + label + "_cuda_initializations") or 0),
            }
        )
    finally:
        db.close()


def cleanup(label: str) -> None:
    db = SessionLocal()
    try:
        transcription = _get_record(db, label)
        if not transcription:
            return
        queue = _queue()
        job_id = f"transcription_{transcription.id}"
        try:
            job = Job.fetch(job_id, connection=queue.connection)
            current = job.get_status(refresh=True)
            current = getattr(current, "value", current)
            if current in {"queued", "started"}:
                raise RuntimeError("Probe job is still active; refusing cleanup")
            for registry in (
                queue.started_job_registry,
                queue.failed_job_registry,
                queue.finished_job_registry,
            ):
                queue.connection.zrem(registry.key, job_id)
            job.delete()
        except NoSuchJobError:
            pass
        db.query(AuditEvent).filter(
            AuditEvent.resource_type == "transcription",
            AuditEvent.resource_id == str(transcription.id),
        ).delete(synchronize_session=False)
        db.delete(transcription)
        db.commit()
        queue.connection.delete(MARKER + label + "_attempts")
        queue.connection.delete(MARKER + label + "_cuda_initializations")
        print("cleaned")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("seed", "work", "work-fork", "work-fork-auto", "recover", "status", "cleanup"))
    parser.add_argument("label")
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    {"seed": lambda: seed(args.label, args.timeout),
     "work": lambda: work(args.label, args.seconds),
     "work-fork": lambda: work(args.label, args.seconds, fork=True),
     "work-fork-auto": lambda: work(args.label, args.seconds, fork=True, automatic_recovery=True),
     "recover": lambda: print(f"recovered={transcription_worker.recover_pending_jobs(_queue())}"),
     "status": lambda: status(args.label),
     "cleanup": lambda: cleanup(args.label)}[args.action]()
