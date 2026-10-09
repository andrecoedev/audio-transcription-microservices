"""Per-account settings and write-only BYOK credentials, never admin secrets."""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserProviderCredential, UserProviderPreferences
from ..security import TokenData, get_authenticated_user
from ..services.audit import append_audit_event
from ..services.provider_credentials import (
    SUPPORTED_PROVIDERS, credential_for, encrypt_credential, providers_view, select_provider,
)
from ..services.rate_limit import enforce_rate_limit
from ..services.transcription_entitlements import require_execution
from ..utils.http_limits import BodyLimitedRoute

router = APIRouter(prefix="/settings/providers", tags=["provider settings"], route_class=BodyLimitedRoute)


class PreferencesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    transcription_provider: Literal["automatic", "whisper", "assemblyai"]
    intelligence_provider: Literal["automatic", "gemini", "groq"]
    use_diarization: bool


class CredentialInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secret: SecretStr

    @field_validator("secret")
    @classmethod
    def validate_secret(cls, value):
        secret = value.get_secret_value()
        if not 8 <= len(secret) <= 4096 or not secret.isascii() or any(c.isspace() for c in secret):
            raise ValueError("Invalid provider credential format")
        return value


@router.get("")
def get_preferences(db: Session = Depends(get_db), user: TokenData = Depends(get_authenticated_user)):
    return providers_view(db, user)


@router.patch("")
def save_preferences(body: PreferencesInput, request: Request, db: Session = Depends(get_db),
                     user: TokenData = Depends(get_authenticated_user)):
    enforce_rate_limit(request, "provider-settings-user", str(user.user_id))
    # Serialize settings changes with credential replacement for this account.
    db.query(User).filter_by(id=user.user_id).with_for_update().one()
    if body.transcription_provider == "assemblyai":
        select_provider(db, user, "assemblyai")
    if body.intelligence_provider != "automatic":
        select_provider(db, user, body.intelligence_provider)
    row = db.get(UserProviderPreferences, user.user_id)
    if row is None:
        row = UserProviderPreferences(user_id=user.user_id)
        db.add(row)
    for name, value in body.model_dump().items():
        setattr(row, name, value)
    db.commit()
    return providers_view(db, user)


def valid_provider(provider):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(404, "Provider not found")


@router.post("/{provider}/credential")
def save_credential(provider: str, body: CredentialInput, request: Request, db: Session = Depends(get_db),
                    user: TokenData = Depends(get_authenticated_user)):
    valid_provider(provider)
    require_execution(db, user.user_id, provider, "user")
    enforce_rate_limit(request, "provider-settings-user", str(user.user_id))
    ciphertext = encrypt_credential(user.user_id, provider, body.secret.get_secret_value())
    db.query(User).filter_by(id=user.user_id).with_for_update().one()
    previous = credential_for(db, user.user_id, provider)
    if previous:
        db.delete(previous)
        db.flush()  # Old queued references become NULL; never use the replacement silently.
    db.add(UserProviderCredential(id=str(uuid4()), user_id=user.user_id, provider=provider, ciphertext=ciphertext))
    append_audit_event(db, event="provider.credential_saved", actor_user_id=user.user_id,
                       resource_type="provider", resource_id=provider, metadata={"provider": provider})
    db.commit()
    return providers_view(db, user)


@router.delete("/{provider}/credential")
def remove_credential(provider: str, request: Request, db: Session = Depends(get_db),
                      user: TokenData = Depends(get_authenticated_user)):
    valid_provider(provider)
    enforce_rate_limit(request, "provider-settings-user", str(user.user_id))
    db.query(User).filter_by(id=user.user_id).with_for_update().one()
    row = credential_for(db, user.user_id, provider)
    if row:
        db.delete(row)
    append_audit_event(db, event="provider.credential_removed", actor_user_id=user.user_id,
                       resource_type="provider", resource_id=provider, metadata={"provider": provider})
    db.commit()
    return providers_view(db, user)
