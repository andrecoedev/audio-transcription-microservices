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
    version: int = Field(ge=0)
    confirmed: bool = False
    hard_stop_usd: Decimal = Field(ge=0, le=1000, decimal_places=8, allow_inf_nan=False)
    alert_usd: Decimal = Field(ge=0, le=1000, decimal_places=8, allow_inf_nan=False)
    reason: Literal["manual_review"]


@router.patch("/admin/providers/assemblyai/budget")
def budget_change(body: BudgetInput, request: Request, db: Session = Depends(get_db),
                  admin: TokenData = Depends(require_admin)):
    enforce_rate_limit(request, "provider-settings-user", str(admin.user_id))
    finance.change_platform_budget(db, **body.model_dump(), actor_user_id=admin.user_id)
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
        "configured_cap_usd": str(budget.limit_cents / 100),
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


class CallReconciliationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    decision: Literal["completed", "error", "not_submitted"]
    reason: Literal["dashboard_verified"]
    provider_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{1,128}$")
    audio_duration_seconds: Decimal | None = Field(default=None, ge=0, le=1000000000, allow_inf_nan=False)


@router.post("/admin/providers/assemblyai/calls/{call_id}/reconcile")
def reconcile_call(call_id: int, body: CallReconciliationInput, request: Request,
                   db: Session = Depends(get_db), admin: TokenData = Depends(require_admin)):
    from rq.exceptions import NoSuchJobError
    from rq.job import Job
    from ..models import TranscriptionJob
    from ..workers.config import get_transcription_queue

    enforce_rate_limit(request, "provider-settings-user", str(admin.user_id))
    budget = finance._budget(db, lock=True)
    call = db.get(PlatformProviderCall, call_id)
    if call is None or call.provider != "assemblyai":
        raise HTTPException(404, "Operação não encontrada.")
    if call.settled_at:
        if call.provider_status != body.decision:
            raise HTTPException(409, "A operação já possui confirmação terminal diferente.")
        return {"reconciled": True}
    if (call.state not in {"reserved", "attempted"} or not call.operation_key
        or (call.state == "reserved" and body.decision != "not_submitted")):
        raise HTTPException(409, "A operação não possui tentativa conciliável.")
    prefix, _, tid = call.operation_key.partition(":")
    if prefix != "transcription" or not tid.isdigit():
        raise HTTPException(409, "A referência histórica exige revisão operacional.")
    job = db.query(TranscriptionJob).filter_by(transcription_id=int(tid)).one_or_none()
    if job and job.status in {"queued", "processing"}:
        raise HTTPException(409, "A transcrição ainda está ativa.")
    try:
        queue = get_transcription_queue()
        queue.connection.ping()
        try:
            running = Job.fetch(f"transcription_{tid}", connection=queue.connection)
        except NoSuchJobError:
            running = None
        status = running.get_status(refresh=True) if running else None
        if getattr(status, "value", status) in {"queued", "started", "deferred", "scheduled"}:
            raise HTTPException(409, "O processamento ainda está ativo na fila.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Não foi possível confirmar o encerramento na fila.") from None
    if body.decision == "not_submitted":
        if call.remote_transcript_id:
            raise HTTPException(409, "Já existe uma referência remota; confira o resultado no painel.")
        if call.released_at is None:
            budget.reserved_cents -= call.reserved_cents
            call.released_at = finance.now_utc()
        call.provider_status = "not_submitted"
        call.settled_at = finance.now_utc()
    else:
        provider_id = body.provider_id or call.remote_transcript_id
        if not provider_id or (body.decision == "completed" and body.audio_duration_seconds is None):
            raise HTTPException(422, "Informe a referência remota e a duração comprovada do sucesso.")
        finance.observe_platform_call(db, call.transcription_id, {"provider_id": provider_id,
            "status": body.decision, "audio_duration_seconds": body.audio_duration_seconds}, call_id=call.id)
    append_audit_event(db, event="provider.call_reconciled", actor_user_id=admin.user_id,
        resource_type="provider_call", resource_id=call.id,
        metadata={"decision": body.decision, "reason": body.reason})
    db.commit()
    return {"reconciled": True}
