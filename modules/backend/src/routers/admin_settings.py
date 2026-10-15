"""Strictly administrative operational configuration, never an ENV editor."""
from fastapi import APIRouter, Depends, Request, Query
from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal
from sqlalchemy.orm import Session

from ..database import get_db
from ..security import TokenData, require_admin
from ..services.beta_settings import (settings_view, initialize_policy, update_policy,
                                     overview, participants_view, settings_history)
from ..services.rate_limit import enforce_rate_limit
from ..utils.http_limits import BodyLimitedRoute

router = APIRouter(prefix="/admin/settings", tags=["admin settings"], route_class=BodyLimitedRoute)


@router.get("")
def get_settings(db: Session = Depends(get_db), admin: TokenData = Depends(require_admin)):
    return settings_view(db)


@router.get("/overview")
def get_overview(db: Session = Depends(get_db), admin: TokenData = Depends(require_admin)):
    from .health import _processing_status
    result = overview(db)
    result["system"].update(_processing_status())
    return result


@router.get("/participants")
def get_participants(db: Session = Depends(get_db), admin: TokenData = Depends(require_admin)):
    return participants_view(db)


@router.get("/accounts")
def search_accounts(q: str = Query(min_length=2, max_length=100), db: Session = Depends(get_db),
                    admin: TokenData = Depends(require_admin)):
    from sqlalchemy import or_
    from ..models import User
    term = q.strip()
    if len(term) < 2:
        from fastapi import HTTPException
        raise HTTPException(422, "Digite pelo menos dois caracteres para buscar uma conta.")
    # Escape LIKE metacharacters; this is bounded account lookup, not content search.
    pattern = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    users = db.query(User).filter(User.is_active.is_(True), or_(
        User.username.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\"))).order_by(User.id).limit(10).all()
    return {"items": [{"user_id": user.id, "username": user.username, "email": user.email} for user in users]}


@router.get("/history")
def get_history(db: Session = Depends(get_db), admin: TokenData = Depends(require_admin)):
    return settings_history(db)


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
