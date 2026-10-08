"""Owner-scoped credential envelopes; secrets never leave API writes/Worker reads."""

import json

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from ..config import settings
from ..models import UserProviderCredential, UserProviderPreferences
from .provider_policy import require_provider_credential
from .platform_budget import platform_budget_has_headroom
from .transcription_entitlements import require_execution

SUPPORTED_PROVIDERS = {"assemblyai", "gemini"}
DEFAULT_PREFERENCES = {"transcription_provider": "automatic", "intelligence_provider": "automatic", "use_diarization": False}


def credential_cipher() -> Fernet:
    key = settings.PROVIDER_CREDENTIAL_ENCRYPTION_KEY
    if not key or key == settings.SECRET_KEY:
        raise HTTPException(503, "Provider credential storage is unavailable")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeError):
        raise HTTPException(503, "Provider credential storage is unavailable") from None


def credential_storage_available() -> bool:
    try:
        credential_cipher()
        return True
    except HTTPException:
        return False


def credential_for(db, user_id, provider):
    return db.query(UserProviderCredential).filter_by(user_id=user_id, provider=provider).one_or_none()


def encrypt_credential(user_id, provider, secret):
    payload = json.dumps({"user_id": user_id, "provider": provider, "secret": secret})
    return credential_cipher().encrypt(payload.encode()).decode("ascii")


def decrypt_credential(db, credential_id, user_id, provider):
    """No fallback, including revoked/replaced credentials and ciphertext swaps."""
    row = db.get(UserProviderCredential, credential_id) if credential_id else None
    if not row or row.user_id != user_id or row.provider != provider:
        raise RuntimeError("User provider credential is unavailable")
    try:
        payload = json.loads(credential_cipher().decrypt(row.ciphertext.encode()))
        if payload["user_id"] != user_id or payload["provider"] != provider:
            raise ValueError("Invalid credential binding")
        secret = payload["secret"]
        if not isinstance(secret, str) or not secret:
            raise ValueError("Invalid credential")
        return secret
    except (InvalidToken, ValueError, KeyError, TypeError, HTTPException):
        raise RuntimeError("User provider credential is unavailable") from None


def preferences_for(db, user_id):
    row = db.get(UserProviderPreferences, user_id)
    return {name: getattr(row, name) for name in DEFAULT_PREFERENCES} if row else dict(DEFAULT_PREFERENCES)


def select_provider(db, user, provider):
    """Return immutable execution provenance, never the secret, to HTTP code."""
    if provider == "whisper":
        require_execution(db, user.user_id, provider, "none")
        return {"provider": provider, "credential_source": "none", "credential_id": None, "credential_user_id": None}
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(422, "Unsupported provider")
    own = credential_for(db, user.user_id, provider)
    if own:
        require_execution(db, user.user_id, provider, "user")
        if not credential_storage_available():
            raise HTTPException(503, "User provider credential is unavailable")
        return {"provider": provider, "credential_source": "user", "credential_id": own.id, "credential_user_id": user.user_id}
    # Platform credentials require an explicit account capability and infrastructure policy.
    require_execution(db, user.user_id, provider, "platform")
    require_provider_credential(user, provider)
    if provider == "gemini" and not (settings.GEMINI_API_KEY_CONFIGURED or settings.GEMINI_API_KEY):
        raise HTTPException(503, "Meeting intelligence is not configured")
    return {"provider": provider, "credential_source": "platform", "credential_id": None, "credential_user_id": None}


def resolve_transcription(db, user, requested):
    provider = requested or preferences_for(db, user.user_id)["transcription_provider"]
    if provider == "automatic":
        # Choice is made before upload/queue, not a retry/fallback on failure.
        provider = "assemblyai" if credential_for(db, user.user_id, "assemblyai") else "whisper"
    if provider not in {"whisper", "assemblyai"}:
        raise HTTPException(400, "Invalid transcription model")
    return select_provider(db, user, provider)


def resolve_intelligence(db, user):
    provider = preferences_for(db, user.user_id)["intelligence_provider"]
    if provider == "automatic":
        provider = "gemini"  # Only the currently supported Intelligence provider.
    return select_provider(db, user, provider)


def providers_view(db, user):
    try:
        require_execution(db, user.user_id, "whisper", "none")
        local_allowed = True
    except HTTPException:
        local_allowed = False
    providers = {"whisper": {"available": local_allowed, "allowed": local_allowed, "configured": local_allowed, "credential_source": "none"}}
    credentials = {}
    for provider in sorted(SUPPORTED_PROVIDERS):
        own = credential_for(db, user.user_id, provider)
        credentials[provider] = {"configured": own is not None, "updated_at": own.updated_at.isoformat() if own else None}
        try:
            require_execution(db, user.user_id, provider, "user")
            byok_allowed = True
        except HTTPException:
            byok_allowed = False
        platform_access = False
        try:
            require_execution(db, user.user_id, provider, "platform")
            require_provider_credential(user, provider)
            if provider == "assemblyai":
                platform_access = platform_budget_has_headroom(db)
            else:
                platform_access = bool(settings.GEMINI_API_KEY_CONFIGURED or settings.GEMINI_API_KEY)
        except HTTPException:
            pass
        try:
            selection = select_provider(db, user, provider)
            allowed, source = True, selection["credential_source"]
            if source == "platform":
                allowed = platform_access
        except HTTPException:
            allowed, source = False, "user" if own else None
        providers[provider] = {"available": True, "allowed": allowed, "configured": allowed,
                               "credential_source": source, "platform_access": platform_access,
                               "byok_allowed": byok_allowed}
    return {"preferences": preferences_for(db, user.user_id), "providers": providers, "credentials": credentials,
            "credential_storage_available": credential_storage_available()}
