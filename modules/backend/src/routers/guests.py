"""Restricted temporary results; existing private routes remain private."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, SecretStr
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import GuestSession, Transcription, TranscriptionOwnership
from ..security import create_access_token, get_authenticated_user
from ..services.guest_sessions import claim_guest_results, get_guest_session, utc
from ..services.rate_limit import enforce_rate_limit
from ..services.provider_policy import require_guest_processing
from ..services.transcription_deletion import ActiveTranscriptionError, delete_transcription_data
from .transcriptions import UploadLimitedRoute

router = APIRouter(prefix="/guest", tags=["guest"], route_class=UploadLimitedRoute)


def guest_policy():
    return {"max_upload_mb": settings.PUBLIC_MAX_UPLOAD_MB,
            "max_audio_seconds": settings.PUBLIC_MAX_AUDIO_SECONDS,
            "allowed_extensions": settings.allowed_extensions_list,
            "jobs_per_session": settings.GUEST_JOBS_PER_SESSION,
            "retention_hours": settings.GUEST_RETENTION_HOURS,
            "mode": "demo", "demo_url": "/guest/demo",
            "provider": None, "diarization": False,
            "can_create_job": False, "blocked_by": "demo_only",
            "unavailable_reason": "Explore o exemplo demonstrativo. Entre para consultar os serviços disponíveis para sua conta."}


@router.get("/policy")
def policy():
    return guest_policy()


@router.get("/demo")
def demo():
    """Public, authored synthetic data only; no DB, queue or provider dependency."""
    path = Path(__file__).resolve().parents[1] / "data" / "guest_demo.json"
    return json.loads(path.read_text(encoding="utf-8"))


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


@router.post("/transcriptions/jobs", deprecated=True)
def create_job():
    # Retire writes, not legacy reads/deletion/claim. No multipart parsing or DB.
    require_guest_processing()


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
