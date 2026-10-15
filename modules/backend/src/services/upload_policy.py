"""Operator-approved size exceptions, independent of plans and admin roles."""

from ..config import settings
from .transcription_entitlements import has_development_local_access


def upload_limit_mb(user_id=None, registration_source="public", development_access=False, *, db=None):
    if development_access:
        return settings.MAX_UPLOAD_SIZE_MB
    if user_id in settings.LARGE_UPLOAD_USER_IDS:
        return min(settings.LARGE_UPLOAD_SIZE_MB, settings.MAX_UPLOAD_SIZE_MB)
    if db is not None and user_id is not None:
        from .beta_settings import round_policy_for_user
        beta = round_policy_for_user(db, user_id)
        if beta:
            return min(beta.max_upload_mb, settings.MAX_UPLOAD_SIZE_MB)
    if registration_source == "public":
        return min(settings.PUBLIC_MAX_UPLOAD_MB, settings.MAX_UPLOAD_SIZE_MB)
    return settings.MAX_UPLOAD_SIZE_MB


def upload_policy(user, *, db=None):
    development_access = has_development_local_access(user)
    from .beta_settings import round_policy_for_user
    beta = round_policy_for_user(db, user.user_id) if db is not None else None
    return {
        "max_upload_mb": upload_limit_mb(user.user_id, user.registration_source, development_access, db=db),
        "allowed_extensions": settings.allowed_extensions_list,
        "development_access": development_access,
        "max_audio_seconds": (
            settings.DEV_LOCAL_MAX_AUDIO_SECONDS if development_access else
            min(beta.max_audio_seconds, settings.AAI_MAX_AUDIO_SECONDS) if beta else
            settings.PUBLIC_MAX_AUDIO_SECONDS if user.registration_source == "public" else None
        ),
    }
