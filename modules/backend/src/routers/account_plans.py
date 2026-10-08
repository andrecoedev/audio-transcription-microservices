"""Private plan balances and explicit, audited administrative assignments."""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from rq.exceptions import NoSuchJobError
from rq.job import Job
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BetaAccessGrant, TranscriptionJob, TranscriptionReservation, User
from ..security import TokenData, get_authenticated_user, require_admin
from ..services.audit import append_audit_event
from ..services.rate_limit import enforce_rate_limit
from ..services.transcription_entitlements import CAPABILITIES, now_utc, plan_view
from ..utils.http_limits import BodyLimitedRoute
from ..workers.config import get_transcription_queue

router = APIRouter(tags=["account plans"], route_class=BodyLimitedRoute)


@router.get("/account/plan")
def current_plan(db: Session = Depends(get_db), user: TokenData = Depends(get_authenticated_user)):
    return plan_view(db, user.user_id)


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: Literal["free", "starter", "business"]
    reason: Literal["beta_test", "operational_access", "user_request"]


class BetaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capabilities: list[str] = Field(min_length=1, max_length=5)
    expires_at: datetime

    @field_validator("capabilities")
    @classmethod
    def valid_capabilities(cls, value):
        if set(value) - CAPABILITIES or len(set(value)) != len(value):
            raise ValueError("Invalid beta permissions")
        return value

    @field_validator("expires_at")
    @classmethod
    def valid_expiry(cls, value):
        if value.tzinfo is None or value <= now_utc():
            raise ValueError("Beta requires a future timezone-aware expiration")
        return value.astimezone(timezone.utc)


def locked_user(db, user_id):
    row = db.query(User).filter_by(id=user_id).with_for_update(key_share=True).one_or_none()
    if row is None:
        raise HTTPException(404, "Conta não encontrada.")
    return row


@router.patch("/admin/accounts/{user_id}/plan")
def assign_plan(user_id: int, body: PlanInput, request: Request, db: Session = Depends(get_db),
                admin: TokenData = Depends(require_admin)):
    enforce_rate_limit(request, "provider-settings-user", str(admin.user_id))
    row = locked_user(db, user_id)
    previous = row.plan
    row.plan = body.plan
    append_audit_event(db, event="account.plan_changed", actor_user_id=admin.user_id,
        resource_type="user", resource_id=user_id, metadata={"previous": previous, "plan": body.plan, "reason": body.reason})
    db.commit()
    return {"user_id": user_id, "plan": row.plan}


@router.post("/admin/accounts/{user_id}/beta", status_code=201)
def grant_beta(user_id: int, body: BetaInput, request: Request, db: Session = Depends(get_db),
               admin: TokenData = Depends(require_admin)):
    enforce_rate_limit(request, "provider-settings-user", str(admin.user_id))
    locked_user(db, user_id)
    # One active grant at a time makes revocation and expiry unambiguous.
    if db.query(BetaAccessGrant).filter(BetaAccessGrant.user_id == user_id,
        BetaAccessGrant.revoked_at.is_(None), BetaAccessGrant.expires_at > now_utc()).count():
        raise HTTPException(409, "Revogue o acesso beta atual antes de conceder outro.")
    row = BetaAccessGrant(id=str(uuid4()), user_id=user_id, granted_by_user_id=admin.user_id,
        capabilities=body.capabilities, expires_at=body.expires_at)
    db.add(row)
    append_audit_event(db, event="account.beta_granted", actor_user_id=admin.user_id,
        resource_type="user", resource_id=user_id, metadata={"grant_id": row.id,
        "capabilities": body.capabilities, "expires_at": body.expires_at.isoformat()})
    db.commit()
    return {"id": row.id, "user_id": user_id, "capabilities": row.capabilities, "expires_at": body.expires_at}


@router.delete("/admin/accounts/{user_id}/beta/{grant_id}")
def revoke_beta(user_id: int, grant_id: str, request: Request, db: Session = Depends(get_db),
                admin: TokenData = Depends(require_admin)):
    enforce_rate_limit(request, "provider-settings-user", str(admin.user_id))
    locked_user(db, user_id)
    row = db.query(BetaAccessGrant).filter_by(id=grant_id, user_id=user_id).one_or_none()
    if row is None:
        raise HTTPException(404, "Acesso beta não encontrado.")
    if row.revoked_at is None:
        row.revoked_at = now_utc()
        append_audit_event(db, event="account.beta_revoked", actor_user_id=admin.user_id,
            resource_type="user", resource_id=user_id, metadata={"grant_id": grant_id})
        db.commit()
    return {"revoked": True}


class ReconciliationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["consumed", "released"]
    reason: Literal["processing_verified", "no_processing_verified"]


@router.post("/admin/transcription-reservations/{reservation_id}/reconcile")
def reconcile(reservation_id: str, body: ReconciliationInput, request: Request,
              db: Session = Depends(get_db), admin: TokenData = Depends(require_admin)):
    enforce_rate_limit(request, "provider-settings-user", str(admin.user_id))
    row = db.get(TranscriptionReservation, reservation_id)
    if row is None:
        raise HTTPException(404, "Reserva não encontrada.")
    if row.user_id:
        locked_user(db, row.user_id)
    db.refresh(row)
    if row.state != "unknown":
        raise HTTPException(409, "Somente uma operação pendente de reconciliação pode ser conciliada.")
    job = db.query(TranscriptionJob).filter_by(transcription_id=row.transcription_id).one_or_none() if row.transcription_id else None
    if job and job.status in {"queued", "processing"}:
        raise HTTPException(409, "A transcrição ainda está ativa.")
    # Check the immutable operation key even if the domain resource was deleted.
    tid = row.operation_key.split(":", 1)[1]
    try:
        queue = get_transcription_queue()
        queue.connection.ping()
        try:
            rq_job = Job.fetch(f"transcription_{tid}", connection=queue.connection)
        except NoSuchJobError:
            rq_job = None
        rq_status = rq_job.get_status() if rq_job else None
        if getattr(rq_status, "value", rq_status) in {"queued", "started", "deferred", "scheduled"}:
            raise HTTPException(409, "O processamento ainda está ativo na fila.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Não foi possível confirmar o encerramento do processamento.") from None
    if body.decision == "consumed" and row.measured_seconds is None:
        raise HTTPException(409, "A duração precisa ser comprovada antes de confirmar consumo.")
    if (body.decision == "consumed") != (body.reason == "processing_verified"):
        raise HTTPException(422, "A justificativa não corresponde à decisão.")
    row.state = body.decision
    append_audit_event(db, event="transcription.reservation_reconciled", actor_user_id=admin.user_id,
        resource_type="reservation", resource_id=row.id, metadata=body.model_dump())
    db.commit()
    # Does not alter metric history or platform spending reservations.
    return {"id": row.id, "state": row.state}
