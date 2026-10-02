"""Persistent local-user authentication and legacy ownership reconciliation."""

import re

from sqlalchemy.orm import Session

from ..config import settings
from ..models import TranscriptionOwnership, User
from ..security import get_password_hash, verify_password


_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,50}$")

USER_SCOPES = [
    "transcribe",
    "meeting_minutes",
    "read_transcriptions",
    "delete_transcriptions",
]
ADMIN_SCOPES = ["manage_keys", *USER_SCOPES]


def _valid_bootstrap_admin_password(password: str) -> bool:
    if settings.AUTH_ADMIN_PASSWORD_HASH:
        return verify_password(password, settings.AUTH_ADMIN_PASSWORD_HASH)
    return bool(
        settings.AUTH_ADMIN_PASSWORD
        and password == settings.AUTH_ADMIN_PASSWORD
    )


def authenticate_local_user(db: Session, username: str, password: str) -> User | None:
    """Authenticate a stored user, or provision the explicitly configured bootstrap user."""
    normalized_username = username.strip()
    if not _USERNAME_RE.fullmatch(normalized_username) or len(password.encode("utf-8")) > 72:
        return None

    user = db.query(User).filter(User.username == normalized_username).one_or_none()
    if user is not None:
        if not user.is_active or not verify_password(password, user.hashed_password):
            return None
        if user.registration_source == "local":
            _resolve_exact_legacy_ownership(db, user)
        return user

    if normalized_username == settings.AUTH_ADMIN_USERNAME:
        if not _valid_bootstrap_admin_password(password):
            return None
        stored_hash = settings.AUTH_ADMIN_PASSWORD_HASH or get_password_hash(password)
        user = User(
            username=normalized_username,
            email=settings.AUTH_ADMIN_EMAIL.strip().lower(),
            hashed_password=stored_hash,
            is_active=True,
            is_superuser=True,
        )
    else:
        return None

    db.add(user)
    db.flush()
    _resolve_exact_legacy_ownership(db, user)
    return user


def _resolve_exact_legacy_ownership(db: Session, user: User) -> int:
    """Map only exact username matches; ambiguous fallback is deliberately absent."""
    return (
        db.query(TranscriptionOwnership)
        .filter(
            TranscriptionOwnership.user_id.is_(None),
            TranscriptionOwnership.owner_sub == user.username,
        )
        .update(
            {TranscriptionOwnership.user_id: user.id},
            synchronize_session=False,
        )
    )


def principal_for_user(user: User) -> dict:
    return {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email,
        # Restrictive transport hint only; permissions still use the database.
        "registration_source": user.registration_source,
        "roles": ["admin"] if user.is_superuser else ["user"],
        "scopes": ADMIN_SCOPES if user.is_superuser else USER_SCOPES,
    }


def register_public_user(db: Session, username: str, email: str, password: str) -> User:
    """Public registration cannot provision an admin or claim a legacy identity."""
    username = username.strip()
    email = email.strip().lower()
    if (
        not _USERNAME_RE.fullmatch(username)
        or username.casefold() == settings.AUTH_ADMIN_USERNAME.casefold()
        or email == settings.AUTH_ADMIN_EMAIL.strip().lower()
        or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
        or not 12 <= len(password.encode("utf-8")) <= 72
    ):
        raise ValueError("Unable to create account with these details")
    legacy = db.query(TranscriptionOwnership.id).filter(
        TranscriptionOwnership.user_id.is_(None),
        TranscriptionOwnership.owner_sub == username,
    ).first()
    if legacy:
        raise ValueError("Unable to create account with these details")
    user = User(username=username, email=email, hashed_password=get_password_hash(password),
                is_active=True, is_superuser=False, registration_source="public")
    db.add(user)
    db.flush()
    return user
