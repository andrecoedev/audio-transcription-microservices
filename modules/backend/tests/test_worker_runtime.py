import subprocess
import sys
from pathlib import Path

import run_worker
from redis import Redis

from src.workers.config import get_transcription_queue


def test_worker_supervises_forked_jobs_without_preloading_engines(monkeypatch):
    connection = object()
    queue = object()
    observed = []

    monkeypatch.setattr(run_worker, "get_redis_connection", lambda: connection)
    monkeypatch.setattr(run_worker, "is_redis_available", lambda current: current is connection)
    monkeypatch.setattr(run_worker, "get_transcription_queue", lambda current: queue)
    monkeypatch.setattr(run_worker, "recover_pending_jobs", lambda current: observed.append("recovery"))
    monkeypatch.setattr(run_worker, "recover_intelligence_jobs", lambda current: observed.append("intelligence-recovery"))
    monkeypatch.setattr(type(run_worker.settings), "validate_startup", lambda self, **_kwargs: [])

    class RecordingWorker:
        def __init__(self, queues, **kwargs):
            assert queues == [queue]
            assert kwargs["connection"] is connection
            assert kwargs["name"].startswith("transcription-worker-")
            observed.append("worker")

        def work(self, **kwargs):
            observed.append("work")

    monkeypatch.setattr(run_worker, "RecoveringWorker", RecordingWorker)
    run_worker.main()

    assert observed == ["recovery", "intelligence-recovery", "worker", "work"]


def test_worker_supervisor_import_does_not_initialize_cuda_stack():
    backend_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; baseline=set(sys.modules); import run_worker; "
            "assert not {'torch', 'pyannote'} & (set(sys.modules)-baseline)",
        ],
        cwd=backend_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_transcription_queue_has_long_job_timeout():
    connection = Redis.from_url("redis://localhost:6379/0")
    queue = get_transcription_queue(connection)
    assert queue._default_timeout == run_worker.settings.TRANSCRIPTION_JOB_TIMEOUT_SECONDS
    assert queue._default_timeout >= 60


def test_worker_periodic_maintenance_reconciles_pending_jobs(monkeypatch):
    queue = object()
    observed = []
    monkeypatch.setattr(
        run_worker.Worker,
        "run_maintenance_tasks",
        lambda self: observed.append("rq-maintenance"),
    )
    monkeypatch.setattr(
        run_worker,
        "recover_pending_jobs",
        lambda current: observed.append(current),
    )
    worker = object.__new__(run_worker.RecoveringWorker)
    monkeypatch.setattr(run_worker, "recover_intelligence_jobs", lambda current: observed.append("intelligence"))
    worker.queues = [queue]

    worker.run_maintenance_tasks()

    assert observed == ["rq-maintenance", queue, "intelligence"]


def test_forked_work_horse_replaces_inherited_pool_before_job(monkeypatch):
    observed = []
    monkeypatch.setattr(run_worker.engine, "dispose", lambda **kwargs: observed.append(kwargs))
    monkeypatch.setattr(run_worker.Worker, "main_work_horse", lambda self, job, queue: observed.append((job, queue)))
    worker = object.__new__(run_worker.RecoveringWorker)
    worker.main_work_horse("job", "queue")
    assert observed == [{"close": False}, ("job", "queue")]
