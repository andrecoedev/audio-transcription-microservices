"""Content-free metrics for the experimental HTTP/RQ harness (stdlib only)."""

import math
from datetime import datetime, timezone


def require_isolated(settings):
    from urllib.parse import urlsplit

    database = urlsplit(settings.DATABASE_URL)
    if (settings.APP_ENV != "test" or database.hostname != "postgres"
            or database.path != "/usagi_whisper_benchmark"
            or settings.REDIS_URL != "redis://redis:6379/0"):
        raise RuntimeError("Benchmark requires its dedicated disposable database and Redis")
    if any(getattr(settings, name, None) for name in
           ("AAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "PROVIDER_CREDENTIAL_ENCRYPTION_KEY")):
        raise RuntimeError("External credentials are forbidden in the benchmark")


def elapsed_between(start, end):
    if start is None or end is None:
        return None
    def aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    seconds = (aware(end) - aware(start)).total_seconds()
    return seconds if seconds >= 0 else None


def number(value):
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError("Invalid nonnegative measurement")
    return value


def calculate(worker, *, upload_seconds, end_to_end_seconds, queue_seconds):
    """Unknown stays null; do not pretend residual time is persistence or ASR."""
    duration = number(worker.get("audio_seconds"))
    processing = number(worker.get("worker_seconds"))
    row = {name: number(worker.get(name)) for name in (
        "engine_initialization_seconds", "conversion_seconds", "asr_seconds",
        "diarization_seconds", "persistence_seconds", "worker_seconds",
        "ram_peak_mib", "cpu_seconds", "temporary_bytes", "audio_seconds")}
    row.update(upload_seconds=number(upload_seconds),
               end_to_end_seconds=number(end_to_end_seconds),
               queue_seconds=number(queue_seconds),
               processing_rtf=processing / duration if processing is not None and duration else None,
               end_to_end_rtf=end_to_end_seconds / duration if duration else None,
               resource_scope="work_horse_process_tree_sampled_100ms",
               cold_definition="new_forked_work_horse_every_job_models_reloaded_disk_cache_not_flushed")
    return row


def hypothesis(segments):
    return " ".join(str(s.get("text", "")) for s in segments).strip()


def utc_now():
    return datetime.now(timezone.utc).isoformat()
