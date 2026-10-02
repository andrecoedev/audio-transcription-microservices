"""Restricted temporary results; existing private routes remain private."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, SecretStr
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import GuestSession, Transcription, TranscriptionOwnership
from ..security import create_access_token, get_authenticated_user
from ..services.guest_sessions import claim_guest_results, get_guest_session, utc
from ..services.rate_limit import enforce_rate_limit
from ..services.transcription_deletion import ActiveTranscriptionError, delete_transcription_data
from .transcriptions import UploadLimitedRoute, enqueue_transcription

router = APIRouter(prefix="/guest", tags=["guest"], route_class=UploadLimitedRoute)


def guest_policy():
    return {"max_upload_mb": settings.PUBLIC_MAX_UPLOAD_MB,
            "max_audio_seconds": settings.PUBLIC_MAX_AUDIO_SECONDS,
            "jobs_per_session": settings.GUEST_JOBS_PER_SESSION,
            "retention_hours": settings.GUEST_RETENTION_HOURS,
            "provider": "assemblyai", "diarization": True,
            "can_create_job": False, "blocked_by": "P4-04",
            "unavailable_reason": "A transcrição para visitantes está temporariamente indisponível enquanto validamos o serviço."}


@router.get("/policy")
def policy():
    return guest_policy()


@router.post("/sessions", status_code=201)
def create_session(request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "guest-session")
    lifetime = timedelta(hours=settings.GUEST_RETENTION_HOURS)
    guest = GuestSession(id=str(uuid4()), expires_at=datetime.now(timezone.utc) + lifetime)
    db.add(guest)
    db.commit()
    return {"guest_token": create_access_token({"sub": guest.id, "purpose": "guest"}, lifetime),
            "expires_at": utc(guest.expires_at).isoformat(), "policy": guest_policy()}


@router.get("/session")
def session(guest: GuestSession = Depends(get_guest_session)):
    return {"expires_at": utc(guest.expires_at).isoformat(), "jobs_created": guest.jobs_created,
            "policy": guest_policy()}


@router.post("/transcriptions/jobs", status_code=202)
async def create_job(request: Request, file: UploadFile = File(...),
                     use_diarization: bool = Form(False), transcription_model: str = Form("assemblyai"),
                     db: Session = Depends(get_db), guest: GuestSession = Depends(get_guest_session)):
    # Atomic reservation also serializes uploads against conversion/cleanup.
    reserved = db.query(GuestSession).filter(
        GuestSession.id == guest.id, GuestSession.claimed_by_user_id.is_(None),
        GuestSession.expires_at > datetime.now(timezone.utc),
        GuestSession.jobs_created < settings.GUEST_JOBS_PER_SESSION,
    ).update({GuestSession.jobs_created: GuestSession.jobs_created + 1}, synchronize_session=False)
    if reserved != 1:
        db.rollback()
        await file.close()
        raise HTTPException(429, "Guest job limit reached; create an account to continue")
    try:
        result = await enqueue_transcription(request, file, use_diarization, transcription_model,
                                             db, None, guest_session=guest)
        result.status_url = f"/guest/transcriptions/{result.id}"
        result.result_url = result.status_url
        return result
    except Exception:
        db.rollback()
        raise


def owned_transcription(db, transcription_id, guest):
    row = db.query(Transcription).join(TranscriptionOwnership).filter(
        Transcription.id == transcription_id, TranscriptionOwnership.guest_session_id == guest.id,
        TranscriptionOwnership.user_id.is_(None),
    ).one_or_none()
    if not row:
        raise HTTPException(404, "Transcription not found")
    return row


@router.get("/transcriptions/{transcription_id}")
def result(transcription_id: int, db: Session = Depends(get_db), guest: GuestSession = Depends(get_guest_session)):
    return owned_transcription(db, transcription_id, guest).to_dict()


@router.delete("/transcriptions/{transcription_id}")
def delete(transcription_id: int, db: Session = Depends(get_db), guest: GuestSession = Depends(get_guest_session)):
    row = owned_transcription(db, transcription_id, guest)
    try:
        delete_transcription_data(db, row, None)
    except ActiveTranscriptionError:
        raise HTTPException(409, "Active transcription jobs cannot be deleted") from None
    return {"deleted": True}


class ClaimRequest(BaseModel):
    guest_token: SecretStr


@router.post("/claim")
def claim(payload: ClaimRequest, db: Session = Depends(get_db), user=Depends(get_authenticated_user)):
    return claim_guest_results(db, payload.guest_token.get_secret_value(), user)
