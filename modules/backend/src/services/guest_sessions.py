"""Signed, expiring guest provenance and atomic conversion to a real account."""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import GuestSession, TranscriptionOwnership, UsageEvent
from ..security import decode_verified_claims, oauth2_scheme
from .audit import append_audit_event


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def verified_guest(db: Session, token: str | None, *, lock=False, allow_claimed=False) -> GuestSession:
    claims = decode_verified_claims(token)
    if not claims or claims.get("purpose") != "guest" or not isinstance(claims.get("sub"), str):
        raise HTTPException(401, "Guest session is invalid or expired")
    query = db.query(GuestSession).filter(GuestSession.id == claims["sub"])
    if lock:
        query = query.with_for_update()
    guest = query.one_or_none()
    if not guest or utc(guest.expires_at) <= datetime.now(timezone.utc) or (
        guest.claimed_by_user_id is not None and not allow_claimed
    ):
        raise HTTPException(401, "Guest session is invalid or expired")
    return guest


def get_guest_session(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    return verified_guest(db, token, lock=True)


def claim_guest_results(db: Session, token: str, user) -> dict:
    guest = verified_guest(db, token, lock=True, allow_claimed=True)
    if guest.claimed_by_user_id is not None:
        if guest.claimed_by_user_id != user.user_id:
            raise HTTPException(403, "Guest session has already been claimed")
        return {"claimed": True, "transferred": 0}
    owners = db.query(TranscriptionOwnership).filter_by(guest_session_id=guest.id).all()
    for owner in owners:
        owner.user_id = user.user_id
        owner.owner_sub = user.username
        owner.guest_session_id = None
    guest.claimed_by_user_id = user.user_id
    db.query(UsageEvent).filter_by(guest_session_id=guest.id, user_id=None).update(
        {UsageEvent.user_id: user.user_id}, synchronize_session=False)
    append_audit_event(db, event="guest.claimed", actor_user_id=user.user_id,
                       metadata={"transcriptions": len(owners)})
    db.commit()
    return {"claimed": True, "transferred": len(owners)}
