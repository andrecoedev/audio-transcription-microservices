"""Persistent analysis lifecycle. Never hold a DB transaction during Gemini."""

import logging
from uuid import uuid4
from datetime import datetime, timezone

from rq.exceptions import NoSuchJobError
from rq.job import Job

from ..config import settings
from ..database import SessionLocal
from ..intelligence_schema import IntelligenceResult, validate_grounding
from ..models import MeetingIntelligence, TranscriptionOwnership
from ..services.usage_metering import UsageRecorder
from ..services.audit import append_audit_event
from ..services.intelligence_provider import get_provider
from ..services.meeting_intelligence import fingerprint
from ..services.meeting_projection import ordered_segments
from ..services.provider_credentials import decrypt_credential
from ..services.transcription_entitlements import require_execution

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
        execution = {"credential_source": row.credential_source, "credential_id": row.credential_id,
                     "credential_user_id": row.credential_user_id, "provider": row.provider}
        owner = db.query(TranscriptionOwnership).filter_by(transcription_id=row.meeting_id).first()
        execution.update(usage_user_id=owner.user_id if owner else None,
                         usage_guest_id=owner.guest_session_id if owner else None,
                         usage_attempt_id=str(uuid4()), meeting_id=row.meeting_id, model=row.model)
        row.usage_attempt_id = execution["usage_attempt_id"]
        row.status = "processing"
        row.started_at = datetime.now(timezone.utc)
        db.commit()
        return {"context": context, "execution": execution}
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
    usage = None
    provider = None
    terminal_status = "failed"
    try:
        claim = _claim(intelligence_id)
        if claim is None:
            return {"id": intelligence_id, "status": "already_claimed_or_deleted"}
        logger.info("Intelligence processing started id=%s", intelligence_id)
        context, execution = claim["context"], claim["execution"]
        usage = UsageRecorder(operation_id=execution["usage_attempt_id"],
            user_id=execution["usage_user_id"], guest_session_id=execution["usage_guest_id"],
            resource_type="meeting", resource_id=execution["meeting_id"], operation="intelligence",
            provider=execution["provider"], credential_source=execution["credential_source"],
            model=execution["model"], session_factory=SessionLocal)
        usage.record("attempt", "attempt", 1, phase="started", status="started")
        if execution["provider"] != "gemini":
            raise RuntimeError("Unsupported intelligence provider")
        authorization_db = SessionLocal()
        try:
            require_execution(authorization_db,
                execution["credential_user_id"] if execution["credential_source"] == "user" else execution["usage_user_id"],
                execution["provider"], execution["credential_source"])
        finally:
            authorization_db.close()
        if execution["credential_source"] == "user":
            credential_db = SessionLocal()
            try:
                secret = decrypt_credential(credential_db, execution["credential_id"],
                                            execution["credential_user_id"], execution["provider"])
            finally:
                credential_db.close()
            provider = get_provider(api_key=secret)
            secret = None
        elif execution["credential_source"] == "platform":
            provider = get_provider()
        else:
            raise RuntimeError("Invalid intelligence credential source")
        if hasattr(provider, "set_usage_observer"):
            provider.set_usage_observer(usage.provider_response)
        usage.record("external_call", "call", 1, phase="submitted", status="unknown")
        raw = provider.generate(context)
        if not isinstance(raw, str) or len(raw) > 1000000:
            raise ValueError("Invalid provider response size/type")
        validated = IntelligenceResult.model_validate_json(raw)
        validate_grounding(validated, context["segments"], context["speakers"])
        completed = _complete(intelligence_id, validated.model_dump(mode="json"))
        terminal_status = "completed" if completed else "failed"
        logger.info("Intelligence processing ended id=%s persisted=%s", intelligence_id, completed)
        return {"id": intelligence_id, "status": "completed" if completed else "deleted_or_failed"}
    except Exception as exc:
        _fail(intelligence_id)
        logger.warning("Intelligence processing failed id=%s error_type=%s", intelligence_id, type(exc).__name__)
        raise RuntimeError(PUBLIC_FAILURE) from None
    finally:
        if provider is not None and hasattr(provider, "set_usage_observer"):
            provider.set_usage_observer(None)
        if usage is not None:
            usage.record("attempt_status", "state", phase="terminal", status=terminal_status)


def recover_intelligence_jobs(queue) -> int:
    """Republish unpublished intents; surface interrupted inference as failed."""
    db = SessionLocal()
    recovered = 0
    try:
        ids = [item[0] for item in db.query(MeetingIntelligence.id).filter(MeetingIntelligence.status.in_(["pending", "processing"]))]
        db.rollback()
        for intelligence_id in ids:
            interrupted_usage = None
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
                if row.usage_attempt_id:
                    owner = db.query(TranscriptionOwnership).filter_by(transcription_id=row.meeting_id).first()
                    interrupted_usage = UsageRecorder(operation_id=row.usage_attempt_id,
                        user_id=owner.user_id if owner else None, guest_session_id=owner.guest_session_id if owner else None,
                        resource_type="meeting", resource_id=row.meeting_id, operation="intelligence",
                        provider=row.provider, credential_source=row.credential_source, model=row.model,
                        session_factory=SessionLocal)
                row.status = "failed"
                row.result = None
                row.error_message = PUBLIC_FAILURE
                append_audit_event(db, event="intelligence.failed", actor_type="system",
                                   resource_type="meeting", resource_id=row.meeting_id,
                                   metadata={"revision": row.revision, "recovery": True})
            db.commit()
            if interrupted_usage:
                interrupted_usage.record("attempt_status", "state", phase="terminal",
                                         status="cancelled" if rq_status in {"canceled", "stopped"} else "unknown")
        return recovered
    except Exception as exc:
        db.rollback()
        logger.warning("Intelligence recovery failed (%s)", type(exc).__name__)
        raise RuntimeError("Intelligence recovery failed") from None
    finally:
        db.close()
