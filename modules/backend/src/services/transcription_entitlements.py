"""Account admission serialized by the User row, independent of usage metering.

The transaction owner commits. Workers never hold these locks during inference.
UTC month is fixed at admission; retry and month rollover cannot reset a hold.
"""

import json
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config import settings
from ..models import BetaAccessGrant, TranscriptionReservation, TranscriptionJob, TranscriptionOwnership, Transcription, User

CAPABILITIES = {"transcription.byok", "transcription.local", "transcription.platform", "intelligence.byok", "intelligence.platform", "intelligence.groq.platform"}
ACTIVE = {"queued", "processing", "started"}
HELD = ACTIVE | {"unknown"}


class PlanLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    monthly_usagi_seconds: int = Field(0, ge=0)
    max_audio_seconds: int = Field(0, ge=0)
    max_stored_bytes: int = Field(0, ge=0)
    max_queued_jobs: int = Field(0, ge=0)
    max_processing_jobs: int = Field(0, ge=0)


def now_utc():
    return datetime.now(timezone.utc)


def month_window(now):
    if now.tzinfo is None:
        raise ValueError("UTC policy requires an aware datetime")
    start = now.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def has_development_local_access(user):
    return bool(settings.APP_ENV == "dev" and settings.DEV_LOCAL_ACCESS_ENABLED
                and settings.LOCAL_TRANSCRIPTION_ENABLED and user
                and getattr(user, "is_active", True)
                and getattr(user, "development_local_access", False))


def development_local_access(db, user_id):
    return has_development_local_access(db.get(User, user_id))


def access(db, user_id, *, now=None, lock=False):
    now = now or now_utc()
    if lock and db.get_bind().dialect.name != "postgresql" and settings.APP_ENV != "test":
        # SQLite ignores row locks. Keep legacy reads, but never claim atomic
        # allowance enforcement on an unsupported processing database.
        raise HTTPException(503, "O banco de processamento precisa ser configurado pelo administrador.")
    query = db.query(User).filter_by(id=user_id)
    # PostgreSQL NO KEY UPDATE serializes admissions without conflicting with
    # FK KEY SHARE locks from concurrent ownership inserts. We never change IDs.
    user = (query.with_for_update(key_share=True) if lock else query).populate_existing().one_or_none()
    if not user or not user.is_active:
        raise HTTPException(403, "A conta não está disponível para processamento.")
    grants = db.query(BetaAccessGrant).filter(BetaAccessGrant.user_id == user_id,
        BetaAccessGrant.revoked_at.is_(None), BetaAccessGrant.expires_at > now).all()
    round_id = settings.AAI_BETA_ROUND_ID.strip()
    caps = set().union(*(set(g.capabilities) for g in grants)) if grants else set()
    # A historical or mismatched grant must never unlock platform spending.
    if not round_id or not any(g.round_id == round_id and "transcription.platform" in g.capabilities for g in grants):
        caps.discard("transcription.platform")
    if user.plan in {"starter", "business"}:
        caps |= {"transcription.byok", "intelligence.byok"}
    if settings.LOCAL_TRANSCRIPTION_ENABLED and settings.LOCAL_TRANSCRIPTION_HOMOLOGATED:
        caps.add("transcription.local")
    else:
        caps.discard("transcription.local")  # Beta never bypasses infrastructure readiness.
    if has_development_local_access(user):
        caps.add("transcription.local")
    try:
        policies = json.loads(settings.PLAN_POLICIES_JSON)
        if not isinstance(policies, dict) or set(policies) - {"free", "starter", "business", "beta"}:
            raise ValueError("Invalid policy")
        policy = PlanLimits.model_validate(policies.get("beta" if grants else user.plan, {}))
    except (ValueError, TypeError, ValidationError):
        raise HTTPException(503, "Os limites de processamento precisam ser configurados pelo administrador.") from None
    return user, caps, policy, grants


def require_execution(db, user_id, provider, credential_source):
    user, caps, _, _ = access(db, user_id)
    if provider == "groq" and credential_source != "platform":
        raise HTTPException(403, "Chave própria para este serviço ainda não está disponível.")
    capability = ("intelligence.groq.platform" if provider == "groq" else
        "transcription.local" if provider == "whisper" else
        ("transcription." if provider == "assemblyai" else "intelligence.") +
        ("byok" if credential_source == "user" else "platform"))
    dev_local = provider == "whisper" and credential_source == "none" and has_development_local_access(user)
    if capability not in caps and not dev_local:
        message = "A transcrição fornecida pela USAGI ainda não está disponível neste ambiente." if provider == "whisper" else "Este serviço exige um plano autorizado ou acesso beta válido."
        raise HTTPException(403, message)


def _rows(db, user_id, period=None):
    query = db.query(TranscriptionReservation).filter_by(user_id=user_id)
    return query.filter_by(period_start=period).all() if period else query.all()


def _total(rows, source, states):
    return sum((row.reserved_seconds for row in rows if row.source == source and row.state in states), Decimal(0))


def plan_view(db, user_id, *, now=None):
    now = now or now_utc()
    user, caps, limits, grants = access(db, user_id, now=now)
    start, end = month_window(now)
    rows = _rows(db, user_id, start.date())
    round_id = settings.AAI_BETA_ROUND_ID.strip()
    round_grants = [g for g in grants if round_id and g.round_id == round_id
                    and "transcription.platform" in g.capabilities]
    beta_capabilities = set().union(*(set(g.capabilities) for g in grants)) if grants else set()
    if not round_grants:
        beta_capabilities.discard("transcription.platform")
    round_rows = [r for r in _rows(db, user_id) if r.round_id == round_id and round_id]
    if round_grants:
        used = _total(round_rows, "usagi", {"consumed"})
        reserved = _total(round_rows, "usagi", HELD)
        round_limit = Decimal(settings.AAI_BETA_ROUND_SECONDS)
        quota = {"limit_seconds": settings.AAI_BETA_ROUND_SECONDS,
                 "consumed_seconds": str(used), "reserved_seconds": str(reserved),
                 "available_seconds": str(max(Decimal(0), round_limit - used - reserved))}
    else:
        monthly = [r for r in rows if r.round_id is None]
        used, reserved = _total(monthly, "usagi", {"consumed"}), _total(monthly, "usagi", HELD)
        quota = {"limit_seconds": limits.monthly_usagi_seconds, "consumed_seconds": str(used),
                 "reserved_seconds": str(reserved), "available_seconds": str(max(Decimal(0), limits.monthly_usagi_seconds - used - reserved))}
    dev_access = has_development_local_access(user)
    result = {"plan": user.plan, "beta": {"capabilities": sorted(beta_capabilities),
        "expires_at": max(_aware(g.expires_at) for g in grants).isoformat()} if grants else None,
        "period_start": start.isoformat(), "renews_at": None if round_grants else end.isoformat(),
        "quota": quota,
        "byok": {"measured_seconds": str(sum((r.measured_seconds or Decimal(0) for r in rows if r.source == "byok" and r.state == "consumed"), Decimal(0))),
                 "pending_seconds": str(_total(rows, "byok", HELD))},
        "limits": limits.model_dump(exclude={"monthly_usagi_seconds"}),
        "local_processing_available": "transcription.local" in caps,
        "development_access": dev_access}
    if round_grants:
        result["period_kind"] = "beta_round"
        result["beta_round"] = {"id": round_id, "limit_seconds": settings.AAI_BETA_ROUND_SECONDS,
            "consumed_seconds": str(used), "reserved_seconds": str(reserved),
            "available_seconds": str(max(Decimal(0), round_limit - used - reserved)),
            "expires_at": max(_aware(g.expires_at) for g in round_grants).isoformat()}
    if dev_access and not round_grants:
        result["quota"]["limit_seconds"] = None
        result["quota"]["available_seconds"] = None
        result["limits"]["max_audio_seconds"] = None
        result["limits"]["max_stored_bytes"] = None
        result["limits"]["max_queued_jobs"] = settings.DEV_LOCAL_MAX_QUEUED_JOBS
        result["limits"]["max_processing_jobs"] = settings.DEV_LOCAL_MAX_PROCESSING_JOBS
        result["technical_max_audio_seconds"] = settings.DEV_LOCAL_MAX_AUDIO_SECONDS
    return result


def reserve_transcription(db, user_id, transcription_id, selection, size_bytes, reference, *, now=None):
    now = now or now_utc()
    user, _, limits, _ = access(db, user_id, now=now, lock=True)
    dev_local = (selection["provider"] == "whisper" and selection["credential_source"] == "none"
                 and has_development_local_access(user))
    operation = f"transcription:{transcription_id}"
    existing = db.query(TranscriptionReservation).filter_by(operation_key=operation).one_or_none()
    if existing:
        if existing.user_id != user_id:
            raise HTTPException(403, "A operação pertence a outra conta.")
        return existing
    require_execution(db, user_id, selection["provider"], selection["credential_source"])
    if not dev_local and min(limits.max_audio_seconds, limits.max_stored_bytes,
            limits.max_queued_jobs, limits.max_processing_jobs) <= 0:
        raise HTTPException(503, "Os limites deste plano ainda não estão configurados para transcrição.")
    rows = _rows(db, user_id)
    # Persisted jobs also include pre-policy jobs; never ignore legacy concurrency.
    queued = db.query(TranscriptionJob).join(TranscriptionOwnership,
        TranscriptionOwnership.transcription_id == TranscriptionJob.transcription_id).filter(
        TranscriptionOwnership.user_id == user_id, TranscriptionJob.status == "queued",
        TranscriptionJob.transcription_id != transcription_id).count()
    max_queued = settings.DEV_LOCAL_MAX_QUEUED_JOBS if dev_local else limits.max_queued_jobs
    if queued >= max_queued:
        raise HTTPException(429, "Sua fila está cheia. Aguarde uma transcrição terminar.")
    storage = sum(r.stored_bytes for r in rows if r.storage_released_at is None)
    # Conservative admission for historical uploads with no exact reservation.
    legacy = db.query(Transcription).join(TranscriptionOwnership).outerjoin(TranscriptionReservation,
        TranscriptionReservation.transcription_id == Transcription.id).filter(
        TranscriptionOwnership.user_id == user_id, TranscriptionReservation.id.is_(None),
        Transcription.id != transcription_id).all()
    storage += sum(math.ceil((r.file_size_mb or 0) * 1024 * 1024) for r in legacy)
    if size_bytes < 0 or (not dev_local and storage + size_bytes > limits.max_stored_bytes):
        raise HTTPException(429, "O limite de armazenamento foi atingido. Exclua arquivos que não precisa manter.")
    start, _ = month_window(now)
    source = "byok" if selection["credential_source"] == "user" else "usagi"
    round_id = (settings.AAI_BETA_ROUND_ID.strip() if selection["provider"] == "assemblyai"
                and selection["credential_source"] == "platform" else "")
    if round_id and "transcription.platform" not in access(db, user_id, now=now)[1]:
        raise HTTPException(403, "Este serviço exige um plano autorizado ou acesso beta válido.")
    monthly = [r for r in rows if r.period_start == start.date() and r.round_id is None]
    remaining = limits.monthly_usagi_seconds - _total(monthly, "usagi", HELD | {"consumed"})
    if dev_local:
        seconds = Decimal(settings.DEV_LOCAL_MAX_AUDIO_SECONDS)
    else:
        if round_id:
            round_rows = [r for r in rows if r.round_id == round_id]
            round_remaining = Decimal(settings.AAI_BETA_ROUND_SECONDS) - _total(round_rows, "usagi", HELD | {"consumed"})
            seconds = min(Decimal(limits.max_audio_seconds), round_remaining)
        else:
            seconds = Decimal(limits.max_audio_seconds) if source == "byok" else min(Decimal(limits.max_audio_seconds), remaining)
    if seconds < 1:
        message = ("A franquia da rodada beta está esgotada; não há renovação automática."
                   if round_id else "Sua franquia mensal está esgotada. Aguarde a renovação.")
        raise HTTPException(429, message)
    row = TranscriptionReservation(id=str(uuid4()), operation_key=operation, transcription_id=transcription_id,
        user_id=user_id, period_start=start.date(), source=source, provider=selection["provider"],
        credential_source=selection["credential_source"], round_id=round_id or None,
        state="queued", reserved_seconds=seconds,
        stored_bytes=size_bytes, input_reference=reference)
    db.add(row)
    db.flush()
    return row


def reservation_for(db, transcription_id):
    return db.query(TranscriptionReservation).filter_by(transcription_id=transcription_id).one_or_none()


def _require_reservation_round(row):
    if row.provider == "assemblyai" and row.credential_source == "platform":
        round_id = settings.AAI_BETA_ROUND_ID.strip()
        if not round_id or row.round_id != round_id:
            raise HTTPException(403, "A reserva não pertence à rodada beta ativa.")
    elif row.round_id is not None:
        raise HTTPException(403, "A reserva possui uma rodada beta incompatível.")


def claim_reservation(db, transcription_id):
    row = reservation_for(db, transcription_id)
    if not row or not row.user_id:
        raise HTTPException(403, "Esta transcrição não possui autorização de processamento válida.")
    user, _, limits, _ = access(db, row.user_id, lock=True)
    db.refresh(row)
    _require_reservation_round(row)
    require_execution(db, row.user_id, row.provider, row.credential_source)
    if row.state != "queued":
        raise HTTPException(409, "A reserva não está disponível para iniciar processamento.")
    running = db.query(TranscriptionJob).join(TranscriptionOwnership,
        TranscriptionOwnership.transcription_id == TranscriptionJob.transcription_id).filter(
        TranscriptionOwnership.user_id == row.user_id, TranscriptionJob.status == "processing",
        TranscriptionJob.transcription_id != transcription_id).count()
    dev_local = (row.provider == "whisper" and row.credential_source == "none"
                 and has_development_local_access(user))
    max_processing = settings.DEV_LOCAL_MAX_PROCESSING_JOBS if dev_local else limits.max_processing_jobs
    if running >= max_processing:
        raise HTTPException(429, "O limite de transcrições simultâneas foi atingido.")
    row.state = "processing"
    return row


def authorize_inference(db, transcription_id, duration):
    row = reservation_for(db, transcription_id)
    if not row or not row.user_id:
        raise HTTPException(403, "Autorização de processamento ausente.")
    user, _, limits, _ = access(db, row.user_id, lock=True)
    db.refresh(row)
    _require_reservation_round(row)
    require_execution(db, row.user_id, row.provider, row.credential_source)
    # Round only to millisecond precision, always upwards; never trust client metadata.
    seconds = Decimal(str(duration))
    if not seconds.is_finite() or seconds <= 0:
        raise HTTPException(422, "Não foi possível verificar a duração do áudio.")
    seconds = seconds.quantize(Decimal("0.001"), rounding=ROUND_CEILING)
    dev_local = (row.provider == "whisper" and row.credential_source == "none"
                 and has_development_local_access(user))
    max_duration = settings.DEV_LOCAL_MAX_AUDIO_SECONDS if dev_local else limits.max_audio_seconds
    if row.state != "processing" or seconds > min(row.reserved_seconds, Decimal(max_duration)):
        raise HTTPException(429, "O áudio excede o tempo disponível para esta transcrição.")
    if row.round_id is not None:
        other_round_rows = db.query(TranscriptionReservation).filter(
            TranscriptionReservation.user_id == row.user_id,
            TranscriptionReservation.round_id == row.round_id,
            TranscriptionReservation.id != row.id,
        ).all()
        consumed_or_held = _total(other_round_rows, "usagi", HELD | {"consumed"})
        if consumed_or_held + seconds > Decimal(settings.AAI_BETA_ROUND_SECONDS):
            raise HTTPException(429, "A franquia da rodada beta foi reduzida e não comporta este áudio.")
    row.measured_seconds = seconds
    row.reserved_seconds = seconds  # Release unused maximum before irreversible inference.
    row.state = "started"
    db.flush()


def finish_reservation(db, transcription_id, *, success=False):
    row = reservation_for(db, transcription_id)
    if row is None:
        return  # Historical completed resources remain readable.
    if row.user_id:
        db.query(User).filter_by(id=row.user_id).with_for_update(key_share=True).one_or_none()
    db.refresh(row)
    if row.state in {"consumed", "released", "unknown"}:
        return
    if success:
        if row.state != "started":
            raise RuntimeError("Result has no authorized inference")
        row.state = "consumed"
    else:
        from ..models import PlatformProviderCall
        call = db.query(PlatformProviderCall).filter_by(transcription_id=transcription_id).one_or_none()
        remote_error = bool(call and call.provider_status == "error" and call.settled_at)
        row.state = "unknown" if row.state == "started" and not remote_error else "released"


def recover_reservation(db, transcription_id):
    row = reservation_for(db, transcription_id)
    if row is None:
        return False  # Do not grandfather a pending unauthorized historical job.
    if row.user_id:
        db.query(User).filter_by(id=row.user_id).with_for_update(key_share=True).one_or_none()
    db.refresh(row)
    if row.state == "started":
        row.state = "unknown"
        return False  # Ambiguous work requires explicit reconciliation, no double inference.
    if row.state == "processing":
        row.state = "queued"  # Before inference; safe retry retains identical hold/month.
    return row.state == "queued"


def release_storage(db, reference):
    db.query(TranscriptionReservation).filter(TranscriptionReservation.input_reference == reference,
        TranscriptionReservation.storage_released_at.is_(None)).update(
        {TranscriptionReservation.storage_released_at: now_utc()}, synchronize_session=False)
