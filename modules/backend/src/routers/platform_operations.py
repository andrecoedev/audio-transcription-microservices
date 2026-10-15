"""Small, administrator-only operational controls; no transcript access."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..security import TokenData, require_admin
from ..services import platform_budget as finance
from ..services.audit import append_audit_event
from ..services.rate_limit import enforce_rate_limit
from ..models import PlatformProviderCall
from ..utils.http_limits import BodyLimitedRoute

router = APIRouter(tags=["platform operations"], route_class=BodyLimitedRoute)


class BalanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    available_usd: Decimal = Field(ge=0, le=1000000, max_digits=18, decimal_places=8, allow_inf_nan=False)
    checked_at: datetime
    key_reference: str = Field(pattern=r"^[a-z][a-z0-9_.:-]{0,63}$")
    project_reference: str = Field(pattern=r"^[a-z][a-z0-9_.:-]{0,63}$")
    exclusive: bool


@router.post("/admin/providers/assemblyai/balance-check")
def balance_check(body: BalanceInput, request: Request, db: Session = Depends(get_db),
                  admin: TokenData = Depends(require_admin)):
    enforce_rate_limit(request, "provider-settings-user", str(admin.user_id))
    budget = finance.record_balance_check(db, **body.model_dump(), actor_user_id=admin.user_id)
    db.commit()
    return {"recorded": True, "checked_at": budget.balance_checked_at,
            "exclusive": budget.balance_exclusive}


class BudgetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hard_stop_usd: Decimal = Field(gt=0, le=1000, decimal_places=8, allow_inf_nan=False)
    alert_usd: Decimal = Field(ge=0, le=1000, decimal_places=8, allow_inf_nan=False)
    reason: Literal["manual_review"]


@router.patch("/admin/providers/assemblyai/budget")
def budget_change(body: BudgetInput, request: Request, db: Session = Depends(get_db),
                  admin: TokenData = Depends(require_admin)):
    enforce_rate_limit(request, "provider-settings-user", str(admin.user_id))
    finance._policy(enabled=False)
    budget = finance._budget(db, create=True, lock=True)
    new_limit, alert = body.hard_stop_usd * 100, body.alert_usd * 100
    if alert > new_limit or new_limit < budget.reserved_cents:
        raise HTTPException(409, "O teto não pode ficar abaixo das reservas existentes ou do alerta.")
    if new_limit > budget.limit_cents:
        finance._valid_balance(budget)
        if new_limit > budget.balance_baseline_cents + budget.balance_cents:
            raise HTTPException(409, "O teto exige uma conferência de saldo suficiente.")
    before = str(budget.limit_cents)
    budget.limit_cents, budget.alert_cents = new_limit, alert
    append_audit_event(db, event="provider.budget_changed", actor_user_id=admin.user_id,
        resource_type="provider", resource_id="assemblyai", metadata={
            "previous_limit_cents": before, "limit_cents": str(new_limit),
            "alert_cents": str(alert), "reason": body.reason})
    db.commit()
    return {"updated": True}


@router.get("/admin/providers/assemblyai/operations")
def operations(db: Session = Depends(get_db), admin: TokenData = Depends(require_admin)):
    budget = finance._budget(db)
    if budget is None:
        return {"configured": False}
    calls = db.query(PlatformProviderCall).filter_by(provider="assemblyai").all()
    attempts = [c for c in calls if c.state == "attempted" and not c.released_at]
    return {"configured": True, "round_id": budget.round_id,
        "hard_stop_usd": str(budget.limit_cents / 100),
        "authorized_usd": str(budget.reserved_cents / 100),
        "attempted_estimate_usd": str(sum((c.reserved_cents for c in attempts), Decimal(0)) / 100),
        "alert_usd": str(budget.alert_cents / 100), "alerted_at": budget.alerted_at,
        "review_required": budget.review_required, "balance_exclusive": budget.balance_exclusive,
        "balance_checked_at": budget.balance_checked_at,
        "external_balance_snapshot_usd": str(budget.balance_cents / 100) if budget.balance_cents is not None else None,
        "key_reference": budget.key_reference, "project_reference": budget.project_reference,
        "calls": {"total": len(calls), "completed": sum(c.provider_status == "completed" for c in calls),
                  "errors": sum(c.provider_status == "error" for c in calls),
                  "unresolved": sum(c.state == "attempted" and c.settled_at is None for c in calls)}}
