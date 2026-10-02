from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .models import TranscriptionOwnership
from .security import TokenData


def is_admin(user: Optional[TokenData]) -> bool:
    return bool(user and "admin" in user.roles)


def ownership_filter(user_id, username, registration_source):
    """Stable ownership; public signup never inherits legacy username data."""
    stable = TranscriptionOwnership.user_id == user_id
    if registration_source != "local":
        return stable
    return or_(stable, TranscriptionOwnership.user_id.is_(None)
               & TranscriptionOwnership.guest_session_id.is_(None)
               & (TranscriptionOwnership.owner_sub == username))


def enforce_transcription_access(
    db: Session,
    transcription_id: int,
    current_user: Optional[TokenData],
    write: bool = False,
):
    """
    Enforce owner-based authorization for a transcription.

    Cross-user and unresolved ownership both return 404 to avoid disclosing
    whether another user's resource exists.
    """
    if not current_user or is_admin(current_user):
        return

    owner = (
        db.query(TranscriptionOwnership)
        .filter(TranscriptionOwnership.transcription_id == transcription_id)
        .first()
    )

    if owner is None:
        raise HTTPException(status_code=404, detail="Transcription not found")

    stable_match = bool(
        current_user.user_id is not None and owner.user_id == current_user.user_id
    )
    exact_legacy_match = bool(
        current_user.registration_source == "local"
        and owner.guest_session_id is None
        and owner.user_id is None
        and current_user.username
        and owner.owner_sub == current_user.username
    )
    if not (stable_match or exact_legacy_match):
        raise HTTPException(status_code=404, detail="Transcription not found")
