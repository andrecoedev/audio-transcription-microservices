"""Audio references and durable cleanup, independent of RQ and ML engines."""

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_

from ..models import ObjectDeletion, TranscriptionJob
from .object_storage import LocalObjectStorage, StorageError
from .usage_storage import deletion_context, record_object_delete
from .usage_metering import reconcile_usage
from .transcription_entitlements import release_storage
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)
_OBJECT_PREFIX = "object:"


def get_audio_storage(directory=None):
    from ..config import settings
    from .storage_lifecycle import upload_directory

    if settings.OBJECT_STORAGE_BACKEND != "local":
        raise StorageError("Configured object storage backend is unsupported")
    return LocalObjectStorage(directory or upload_directory())


def input_reference(job):
    if job.input_object_key:
        return _OBJECT_PREFIX + job.input_object_key
    return job.input_path or None


@contextmanager
def materialize_input(claim):
    if claim.get("input_object_key"):
        with get_audio_storage().materialize(claim["input_object_key"]) as path:
            yield path
    else:
        # Compatibility only: legacy paths originate in trusted persisted jobs,
        # never in HTTP parameters. Do not reinterpret them as object keys.
        yield Path(claim["input_path"])


def schedule_audio_cleanup(db, reference):
    """Insert intent in the caller's transaction; never commit domain changes."""
    if not reference:
        return
    if db.query(ObjectDeletion.id).filter_by(reference=reference).first():
        return
    try:
        with db.begin_nested():
            db.add(ObjectDeletion(reference=reference))
            db.flush()
    except IntegrityError:
        # Another terminal/deletion transaction already scheduled this object.
        if not db.query(ObjectDeletion.id).filter_by(reference=reference).first():
            raise


def _active_reference(db, reference):
    query = db.query(TranscriptionJob.id).filter(
        TranscriptionJob.status.in_(["queued", "processing"])
    )
    if reference.startswith(_OBJECT_PREFIX):
        query = query.filter(TranscriptionJob.input_object_key == reference[len(_OBJECT_PREFIX):])
    else:
        query = query.filter(or_(TranscriptionJob.input_path == reference,
                                  TranscriptionJob.input_object_key == Path(reference).name))
    return query.first() is not None


def retry_audio_cleanup(db, *, reference=None, apply=False, storage=None, limit=100):
    """Idempotent outbox drain. Missing objects succeed; failures remain durable.

    Row locking serializes maintenance runners. No active input is removed.
    External deletion happens only for an intent committed by its caller.
    """
    query = db.query(ObjectDeletion).order_by(ObjectDeletion.id)
    if reference is not None:
        query = query.filter(ObjectDeletion.reference == reference)
    if apply:
        query = query.with_for_update(skip_locked=True)
    rows = query.limit(limit).all()
    result = {"pending": len(rows), "deleted": 0, "failed": 0,
              "active_preserved": 0, "dry_run": not apply}
    for row in rows:
        if _active_reference(db, row.reference):
            result["active_preserved"] += 1
            continue
        if not apply:
            continue
        row.attempts += 1
        row.last_attempt_at = datetime.now(timezone.utc)
        usage_context = deletion_context(db, row.reference)
        try:
            if row.reference.startswith(_OBJECT_PREFIX):
                (storage or get_audio_storage()).delete(row.reference[len(_OBJECT_PREFIX):])
            else:
                Path(row.reference).unlink(missing_ok=True)
        except (OSError, StorageError):
            logger.warning("Audio cleanup deferred; durable retry retained")
            result["failed"] += 1
        else:
            # Storage accounting follows the successful deletion itself. A
            # failed usage journal must not keep deleted bytes reserved.
            release_storage(db, row.reference)
            # Capture a durable measurement before discarding the retry intent.
            # On journal failure, the missing object succeeds on the next retry.
            if record_object_delete(db, usage_context, datetime.now(timezone.utc)):
                db.delete(row)
                result["deleted"] += 1
            else:
                result["failed"] += 1
    if apply:
        db.commit()
        reconcile_usage(apply=True, limit=100, session_factory=sessionmaker(bind=db.get_bind()))
    return result


def cleanup_after_commit(db, references, *, storage=None):
    result = {"deleted": 0, "failed": 0}
    for reference in set(filter(None, references)):
        try:
            attempt = retry_audio_cleanup(db, reference=reference, apply=True, storage=storage)
        except Exception as exc:
            db.rollback()
            logger.warning("Audio cleanup retry deferred (%s)", type(exc).__name__)
            result["failed"] += 1
            continue
        for key in result:
            result[key] += attempt[key]
    return result
