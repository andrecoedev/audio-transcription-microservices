"""Run the EXISTING supervised Worker with isolated, process-local instrumentation.

Never used by production. No model is loaded before fork. No new queue/ledger.
"""

import importlib.metadata
import json
import logging
import os
from pathlib import Path
import threading
import time

from pipeline_metrics import require_isolated


class Sampler:
    def __init__(self):
        import psutil
        self.psutil = psutil
        self.root = psutil.Process()
        self.peak = 0
        self.cpu = {}
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample_once(self):
        rss = 0
        for process in [self.root, *self.root.children(recursive=True)]:
            try:
                rss += process.memory_info().rss
                clock = process.cpu_times()
                self.cpu[process.pid] = max(self.cpu.get(process.pid, 0), clock.user + clock.system)
            except self.psutil.Error:
                continue
        self.peak = max(self.peak, rss)

    def sample(self):
        while not self.stop.wait(0.1):
            self.sample_once()

    def __enter__(self):
        self.sample_once()
        self.baseline = sum(self.cpu.values())
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=2)
        self.sample_once()


def main():
    from src.config import settings
    require_isolated(settings)
    from src.workers import transcription_worker as worker
    from src.services.transcription_processing_service import TranscriptionProcessingService
    from run_worker import main as run_supervisor

    original_job = worker.process_transcription_job_sync
    original_init = worker.initialize_worker_engines
    original_process = TranscriptionProcessingService.process_transcription
    original_persist = worker._persist_completed_job
    metrics = {}

    def initialize(*args, **kwargs):
        started = time.monotonic()
        try:
            status = original_init(*args, **kwargs)
            from src import engine_registry
            engine = engine_registry.whisper_engine
            if engine is not None and (engine.device != "cpu" or engine.compute_type != "int8"):
                raise RuntimeError("CPU INT8 benchmark device mismatch")
            return status
        finally:
            metrics["engine_initialization_seconds"] = time.monotonic() - started

    def process(self, *args, **kwargs):
        result = original_process(self, *args, **kwargs)
        metrics.update(audio_seconds=result.duration_seconds,
                       conversion_seconds=result.conversion_seconds,
                       asr_seconds=result.transcription_seconds,
                       diarization_seconds=result.diarization_seconds,
                       temporary_bytes=result.temporary_bytes)
        return result

    def persist(*args, **kwargs):
        started = time.monotonic()
        try:
            return original_persist(*args, **kwargs)
        finally:
            metrics["persistence_seconds"] = time.monotonic() - started

    def job(transcription_id):
        metrics.clear()
        started = time.monotonic()
        try:
            with Sampler() as sampler:
                return original_job(transcription_id)
        finally:
            metrics.update(worker_seconds=time.monotonic() - started,
                           ram_peak_mib=sampler.peak / 1024**2,
                           cpu_seconds=max(0, sum(sampler.cpu.values()) - sampler.baseline))
            # Numeric ID is controlled by PostgreSQL; output is content-free.
            destination = Path("/evidence") / f"worker-{int(transcription_id)}.json"
            temporary = destination.with_suffix(f".{os.getpid()}.tmp")
            try:
                temporary.write_text(json.dumps(metrics), encoding="utf-8")
                os.replace(temporary, destination)
            except OSError as error:
                # Instrumentation may become unknown, never reverse a persisted result.
                logging.getLogger(__name__).warning("Benchmark telemetry unavailable (%s)", type(error).__name__)

    worker.initialize_worker_engines = initialize
    worker._persist_completed_job = persist
    TranscriptionProcessingService.process_transcription = process
    worker.process_transcription_job_sync = job
    # Record resolved versions, not dependency ranges from a requirements file.
    versions = {p: importlib.metadata.version(p) for p in
                ("faster-whisper", "ctranslate2", "torch", "pyannote.audio", "rq", "psutil")}
    runtime = dict(packages=versions, device="cpu", compute_type="int8", model="small",
                   language=settings.WHISPER_LANGUAGE, beam_size=settings.WHISPER_BEAM_SIZE,
                   cpu_threads=settings.WHISPER_CPU_THREADS,
                   decode_chunk_seconds=settings.WHISPER_MAX_DECODE_CHUNK_SECONDS,
                   vad_filter=False, condition_on_previous_text=False,
                   temperature=0.0, force_cpu=settings.FORCE_CPU,
                   min_segment_duration=settings.MIN_SEGMENT_DURATION,
                   silence_threshold=settings.SILENCE_THRESHOLD,
                   offline=True)
    for key, path in (("memory_limit_bytes", "/sys/fs/cgroup/memory.max"),
                      ("cpu_quota_period", "/sys/fs/cgroup/cpu.max")):
        file = Path(path)
        runtime[key] = file.read_text().strip() if file.is_file() else None
    Path("/evidence/runtime.json").write_text(json.dumps(runtime), encoding="utf-8")
    run_supervisor()


if __name__ == "__main__":
    main()
