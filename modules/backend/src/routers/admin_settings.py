"""Strictly administrative operational configuration, never an ENV editor."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal
from sqlalchemy.orm import Session

from ..database import get_db
from ..security import TokenData, require_admin
from ..services.beta_settings import settings_view, initialize_policy, update_policy
from ..services.rate_limit import enforce_rate_limit
from ..utils.http_limits import BodyLimitedRoute

router = APIRouter(prefix="/admin/settings", tags=["admin settings"], route_class=BodyLimitedRoute)


@router.get("")
def get_settings(db: Session = Depends(get_db), admin: TokenData = Depends(require_admin)):
    return settings_view(db)


class RevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    version: int = Field(ge=0)
    confirmed: bool = False


class BetaInput(RevisionInput):
    enabled: bool | None = None
    round_name: str | None = Field(default=None, min_length=1, max_length=80)
    round_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.:-]{0,63}$")
    max_participants: int | None = Field(default=None, ge=1, le=5)
    quota_minutes_per_participant: int | None = Field(default=None, ge=0, le=600)


class AssemblyInput(RevisionInput):
    platform_enabled: bool | None = None
    hard_stop_usd: Decimal | None = Field(default=None, strict=False, ge=0, le=1000, decimal_places=8, allow_inf_nan=False)
    alert_usd: Decimal | None = Field(default=None, strict=False, ge=0, le=1000, decimal_places=8, allow_inf_nan=False)


class LimitsInput(RevisionInput):
    max_audio_seconds: int | None = Field(default=None, ge=1, le=600)
    max_upload_mb: int | None = Field(default=None, ge=1, le=100)
    max_stored_bytes: int | None = Field(default=None, ge=0, le=1099511627776)
    max_queued_per_account: int | None = Field(default=None, ge=1, le=100)
    max_processing_per_account: int | None = Field(default=None, ge=1, le=10)
    max_platform_queued: int | None = Field(default=None, ge=1, le=100)
    max_platform_processing: int | None = Field(default=None, ge=1, le=10)


@router.post("/initialize")
def initialize(body: RevisionInput, request: Request, db: Session = Depends(get_db),
               admin: TokenData = Depends(require_admin)):
    enforce_rate_limit(request, "provider-settings-user", str(admin.user_id))
    initialize_policy(db, **body.model_dump(), actor_user_id=admin.user_id)
    db.commit()
    return settings_view(db)


def save(section, body, request, db, admin):
    enforce_rate_limit(request, "provider-settings-user", str(admin.user_id))
    fields = body.model_dump(exclude_unset=True, exclude={"version", "confirmed"})
    if any(value is None for value in fields.values()):
        from fastapi import HTTPException
        raise HTTPException(422, "Campos editáveis não aceitam valor nulo.")
    update_policy(db, section=section, changes={f"{section}.{key}": value for key, value in fields.items()},
        version=body.version, confirmed=body.confirmed, actor_user_id=admin.user_id)
    db.commit()
    return settings_view(db)


@router.patch("/beta")
def save_beta(body: BetaInput, request: Request, db: Session = Depends(get_db), admin: TokenData = Depends(require_admin)):
    return save("beta", body, request, db, admin)


@router.patch("/assemblyai")
def save_assemblyai(body: AssemblyInput, request: Request, db: Session = Depends(get_db), admin: TokenData = Depends(require_admin)):
    return save("assemblyai", body, request, db, admin)


@router.patch("/limits")
def save_limits(body: LimitsInput, request: Request, db: Session = Depends(get_db), admin: TokenData = Depends(require_admin)):
    return save("limits", body, request, db, admin)
