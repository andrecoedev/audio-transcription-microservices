"""Idempotent file cleanup and reconciliation for worker-shared audio storage."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..models import AuditEvent, Transcription, TranscriptionJob
from .audit import append_audit_event


logger = logging.getLogger(__name__)


def upload_directory() -> Path:
    configured = Path(settings.AUDIO_UPLOAD_DIRECTORY)
    if configured.is_absolute():
        return configured.resolve()
    return (Path(__file__).resolve().parents[2] / configured).resolve()


def delete_file_idempotently(path: str | Path | None) -> bool:
    """Delete one exact regular file. Missing files are already clean."""
    if not path:
        return False
    candidate = Path(path)
    try:
        existed = candidate.is_file() or candidate.is_symlink()
        candidate.unlink(missing_ok=True)
        return existed
    except OSError:
        logger.error("Unable to remove managed audio file")
        return False


def reconcile_orphaned_uploads(
    db: Session,
    *,
    directory: Path | None = None,
    older_than_hours: int | None = None,
    apply: bool = False,
    now: datetime | None = None,
) -> dict:
    """Find stale files not referenced by queued/processing jobs.

    Dry-run is the default. Symlinks and non-files are never followed/deleted.
    """
    root = (directory or upload_directory()).resolve()
    ttl_hours = older_than_hours or settings.AUDIO_ORPHAN_RETENTION_HOURS
    if ttl_hours <= 0:
        raise ValueError("older_than_hours must be greater than zero")
    if not root.exists():
        return {"scanned": 0, "candidates": 0, "deleted": 0, "failed": 0, "dry_run": not apply}

    active_paths = {
        str(Path(value).resolve())
        for (value,) in (
            db.query(TranscriptionJob.input_path)
            .filter(TranscriptionJob.status.in_(["queued", "processing"]))
            .all()
        )
    }
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=ttl_hours)
    scanned = candidates = deleted = failed = 0

    for candidate in root.iterdir():
        if candidate.is_symlink() or not candidate.is_file():
            continue
        scanned += 1
        modified = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
        if modified > cutoff or str(candidate.resolve()) in active_paths:
            continue
        candidates += 1
        if apply:
            if delete_file_idempotently(candidate):
                deleted += 1
            elif candidate.exists():
                failed += 1

    return {
        "scanned": scanned,
        "candidates": candidates,
        "deleted": deleted,
        "failed": failed,
        "dry_run": not apply,
    }


def apply_database_retention(
    db: Session,
    *,
    apply: bool = False,
    now: datetime | None = None,
) -> dict:
    """Apply separately configured result and audit retention policies.

    Zero means intentionally indefinite. The operation is dry-run-first and
    file cleanup occurs only after the database transaction commits.
    """
    reference_time = now or datetime.now(timezone.utc)
    transcriptions = []
    if settings.TRANSCRIPTION_RETENTION_DAYS > 0:
        cutoff = reference_time - timedelta(days=settings.TRANSCRIPTION_RETENTION_DAYS)
        transcriptions = (
            db.query(Transcription)
            .filter(
                Transcription.created_at < cutoff,
                Transcription.status.in_(["completed", "failed"]),
                ~Transcription.job.has(
                    TranscriptionJob.status.in_(["queued", "processing"])
                ),
            )
            .order_by(Transcription.id)
            .all()
        )
    audit_query = db.query(AuditEvent)
    audit_candidates = 0
    audit_cutoff = None
    if settings.AUDIT_RETENTION_DAYS > 0:
        audit_cutoff = reference_time - timedelta(days=settings.AUDIT_RETENTION_DAYS)
        audit_candidates = audit_query.filter(AuditEvent.timestamp < audit_cutoff).count()

    result = {
        "transcription_candidates": len(transcriptions),
        "audit_candidates": audit_candidates,
        "transcriptions_deleted": 0,
        "audit_events_deleted": 0,
        "files_cleaned": 0,
        "files_failed": 0,
        "dry_run": not apply,
    }
    if not apply:
        return result

    paths = [row.job.input_path for row in transcriptions if row.job and row.job.input_path]
    for transcription in transcriptions:
        append_audit_event(
            db,
            event="transcription.deleted",
            actor_type="system",
            resource_type="transcription",
            resource_id=transcription.id,
            metadata={"reason": "retention"},
        )
        db.delete(transcription)
    if audit_cutoff is not None:
        result["audit_events_deleted"] = audit_query.filter(
            AuditEvent.timestamp < audit_cutoff
        ).delete(synchronize_session=False)
    db.commit()
    result["transcriptions_deleted"] = len(transcriptions)
    for path in paths:
        if delete_file_idempotently(path):
            result["files_cleaned"] += 1
        elif Path(path).exists():
            result["files_failed"] += 1
    return result
