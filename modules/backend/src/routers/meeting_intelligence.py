"""Durable, asynchronous owner-scoped meeting analysis requests."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..authorization import enforce_transcription_access
from ..config import settings
from ..database import get_db
from ..models import Meeting, MeetingIntelligence
from ..security import TokenData, require_scope
from ..services.audit import append_audit_event
from ..services.meeting_intelligence import fingerprint, latest_revision, metadata_view, snapshot
from ..services.rate_limit import enforce_rate_limit
from ..workers.config import get_transcription_queue, is_redis_available

router = APIRouter(prefix="/meetings", tags=["meeting intelligence"])
logger = logging.getLogger(__name__)


def owned_meeting(db, meeting_id, user, *, lock=False):
    query = db.query(Meeting).filter_by(id=meeting_id)
    if lock:
        query = query.with_for_update()
    meeting = query.first()
    if not meeting:
        raise HTTPException(404, "Meeting not found")
    enforce_transcription_access(db, meeting_id, user)
    return meeting


def request_generation(meeting_id, request, response, db, user, *, regenerate):
    meeting = owned_meeting(db, meeting_id, user, lock=True)
    current = latest_revision(db, meeting_id)
    if current and (current.status in {"pending", "processing"} or (current.status == "completed" and not regenerate)):
        response.status_code = 200 if current.status == "completed" else 202
        return metadata_view(current)
    source, segments = snapshot(meeting)
    if meeting.transcription.status != "completed" or not any(item.get("text", "").strip() for item in segments):
        raise HTTPException(422, "A completed meeting with transcript is required")
    if sum(len(item.get("text", "")) for item in segments) > settings.INTELLIGENCE_MAX_INPUT_CHARACTERS:
        raise HTTPException(422, "Meeting transcript exceeds analysis input limit")
    if not (settings.GEMINI_API_KEY_CONFIGURED or settings.GEMINI_API_KEY):
        raise HTTPException(503, "Meeting intelligence is not configured")
    enforce_rate_limit(request, "job-user", str(user.user_id))
    try:
        queue = get_transcription_queue()
        if not is_redis_available(queue.connection):
            raise RuntimeError("Redis unavailable")
    except Exception:
        raise HTTPException(503, "Processing service temporarily unavailable") from None
    row = MeetingIntelligence(
        meeting_id=meeting_id, revision=current.revision + 1 if current else 1,
        schema_version="1", provider="gemini", model=settings.GEMINI_MODEL,
        status="pending", source_metadata=source, input_fingerprint=fingerprint(source, segments),
    )
    db.add(row)
    db.flush()
    append_audit_event(db, event="intelligence.requested", actor_user_id=user.user_id,
                       resource_type="meeting", resource_id=meeting_id,
                       metadata={"revision": row.revision})
    db.commit()  # Durable intent before Redis publication; recovery covers the gap.
    try:
        queue.enqueue("src.workers.meeting_intelligence_worker.process_intelligence_job", row.id,
                      job_id=f"meeting_intelligence_{row.id}",
                      job_timeout=settings.MEETING_MINUTES_TIMEOUT_SECONDS,
                      result_ttl=settings.MEETING_MINUTES_TIMEOUT_SECONDS)
    except Exception:
        # Redis may have accepted the message before the client lost its ACK.
        # Keep the durable intent pending; recovery inspects RQ before republishing.
        logger.warning("Intelligence queue publication failed id=%s", row.id)
        raise HTTPException(503, "Processing service temporarily unavailable") from None
    response.status_code = 202
    logger.info("Intelligence requested meeting_id=%s revision=%s", meeting_id, row.revision)
    return metadata_view(row)


@router.post("/{meeting_id}/intelligence")
def generate(meeting_id: int, request: Request, response: Response, db: Session = Depends(get_db),
             user: TokenData = Depends(require_scope("meeting_minutes"))):
    return request_generation(meeting_id, request, response, db, user, regenerate=False)


@router.post("/{meeting_id}/intelligence/regenerate")
def regenerate(meeting_id: int, request: Request, response: Response, db: Session = Depends(get_db),
               user: TokenData = Depends(require_scope("meeting_minutes"))):
    return request_generation(meeting_id, request, response, db, user, regenerate=True)


@router.get("/{meeting_id}/intelligence/status")
def status(meeting_id: int, db: Session = Depends(get_db), user: TokenData = Depends(require_scope("read_transcriptions"))):
    owned_meeting(db, meeting_id, user)
    rows = db.query(MeetingIntelligence).filter_by(meeting_id=meeting_id).order_by(MeetingIntelligence.revision.desc()).all()
    last_completed = next((item.revision for item in rows if item.status == "completed"), None)
    return {"configured": bool(settings.GEMINI_API_KEY_CONFIGURED or settings.GEMINI_API_KEY),
            "generation": metadata_view(rows[0]) if rows else None,
            "completed_revision": last_completed, "revisions": [metadata_view(item) for item in rows]}


@router.get("/{meeting_id}/intelligence/result")
def result(meeting_id: int, revision: int | None = None, db: Session = Depends(get_db),
           user: TokenData = Depends(require_scope("read_transcriptions"))):
    meeting = owned_meeting(db, meeting_id, user)
    query = db.query(MeetingIntelligence).filter_by(meeting_id=meeting_id, status="completed")
    if revision is not None:
        query = query.filter_by(revision=revision)
    row = query.order_by(MeetingIntelligence.revision.desc()).first()
    if not row:
        raise HTTPException(404, "Completed meeting analysis not found")
    _, segments = snapshot(meeting)
    # Timestamp references are resolved from the immutable canonical transcript.
    references = [{"segment_order": item["order"], "start": item["start"], "end": item["end"]} for item in segments]
    return {**metadata_view(row), "content": row.result, "references": references, "source": row.source_metadata}
