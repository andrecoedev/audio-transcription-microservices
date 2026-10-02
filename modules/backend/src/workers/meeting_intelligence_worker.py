"""Persistent analysis lifecycle. Never hold a DB transaction during Gemini."""

import logging
from datetime import datetime, timezone

from rq.exceptions import NoSuchJobError
from rq.job import Job

from ..config import settings
from ..database import SessionLocal
from ..intelligence_schema import IntelligenceResult, validate_grounding
from ..models import MeetingIntelligence
from ..services.audit import append_audit_event
from ..services.intelligence_provider import get_provider
from ..services.meeting_intelligence import fingerprint
from ..services.meeting_projection import ordered_segments

logger = logging.getLogger(__name__)
PUBLIC_FAILURE = "Meeting analysis failed; a new attempt can be requested"


def _fail(intelligence_id):
    db = SessionLocal()
    try:
        row = db.query(MeetingIntelligence).filter_by(id=intelligence_id).with_for_update().first()
        if row and row.status in {"pending", "processing"}:
            row.status = "failed"
            row.result = None
            row.error_message = PUBLIC_FAILURE
            append_audit_event(db, event="intelligence.failed", actor_type="system",
                               resource_type="meeting", resource_id=row.meeting_id,
                               metadata={"revision": row.revision})
            db.commit()
    except Exception:
        db.rollback()
        logger.error("Unable to persist intelligence failure id=%s", intelligence_id)
    finally:
        db.close()


def _claim(intelligence_id):
    db = SessionLocal()
    try:
        row = db.query(MeetingIntelligence).filter_by(id=intelligence_id).with_for_update().first()
        if not row or row.status != "pending":
            return None
        segments = ordered_segments(row.meeting.transcription.segments)
        context = {**row.source_metadata, "segments": segments}
        if fingerprint(row.source_metadata, segments) != row.input_fingerprint:
            raise ValueError("Source transcript changed")
        if row.model != settings.GEMINI_MODEL:
            raise ValueError("Provider model configuration mismatch")
        row.status = "processing"
        row.started_at = datetime.now(timezone.utc)
        db.commit()
        return context
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _complete(intelligence_id, content):
    db = SessionLocal()
    try:
        row = db.query(MeetingIntelligence).filter_by(id=intelligence_id).with_for_update().first()
        if not row or row.status != "processing":
            return False  # Deleted, recovered, or superseded; never resurrect a Meeting.
        row.result = content
        row.status = "completed"
        row.error_message = None
        row.completed_at = datetime.now(timezone.utc)
        append_audit_event(db, event="intelligence.completed", actor_type="system",
                           resource_type="meeting", resource_id=row.meeting_id,
                           metadata={"revision": row.revision})
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def process_intelligence_job(intelligence_id: int) -> dict:
    try:
        context = _claim(intelligence_id)
        if context is None:
            return {"id": intelligence_id, "status": "already_claimed_or_deleted"}
        logger.info("Intelligence processing started id=%s", intelligence_id)
        raw = get_provider().generate(context)
        if not isinstance(raw, str) or len(raw) > 1000000:
            raise ValueError("Invalid provider response size/type")
        validated = IntelligenceResult.model_validate_json(raw)
        validate_grounding(validated, context["segments"], context["speakers"])
        completed = _complete(intelligence_id, validated.model_dump(mode="json"))
        logger.info("Intelligence processing ended id=%s persisted=%s", intelligence_id, completed)
        return {"id": intelligence_id, "status": "completed" if completed else "deleted_or_failed"}
    except Exception as exc:
        _fail(intelligence_id)
        logger.warning("Intelligence processing failed id=%s error_type=%s", intelligence_id, type(exc).__name__)
        raise RuntimeError(PUBLIC_FAILURE) from None


def recover_intelligence_jobs(queue) -> int:
    """Republish unpublished intents; surface interrupted inference as failed."""
    db = SessionLocal()
    recovered = 0
    try:
        ids = [item[0] for item in db.query(MeetingIntelligence.id).filter(MeetingIntelligence.status.in_(["pending", "processing"]))]
        db.rollback()
        for intelligence_id in ids:
            row = db.query(MeetingIntelligence).filter_by(id=intelligence_id).with_for_update(skip_locked=True).first()
            if not row or row.status not in {"pending", "processing"}:
                db.rollback()
                continue
            rq_id = f"meeting_intelligence_{row.id}"
            try:
                rq_job = Job.fetch(rq_id, connection=queue.connection)
            except NoSuchJobError:
                rq_job = None
            rq_status = rq_job.get_status(refresh=True) if rq_job else None
            rq_status = getattr(rq_status, "value", rq_status)
            if rq_status in {"queued", "started", "scheduled", "deferred"}:
                db.rollback()
                continue
            if row.status == "pending" and rq_job is None:
                queue.enqueue("src.workers.meeting_intelligence_worker.process_intelligence_job", row.id,
                              job_id=rq_id, job_timeout=settings.MEETING_MINUTES_TIMEOUT_SECONDS,
                              result_ttl=settings.MEETING_MINUTES_TIMEOUT_SECONDS)
                recovered += 1
            else:
                row.status = "failed"
                row.result = None
                row.error_message = PUBLIC_FAILURE
                append_audit_event(db, event="intelligence.failed", actor_type="system",
                                   resource_type="meeting", resource_id=row.meeting_id,
                                   metadata={"revision": row.revision, "recovery": True})
            db.commit()
        return recovered
    except Exception as exc:
        db.rollback()
        logger.warning("Intelligence recovery failed (%s)", type(exc).__name__)
        raise RuntimeError("Intelligence recovery failed") from None
    finally:
        db.close()
