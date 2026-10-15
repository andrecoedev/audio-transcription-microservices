"""Closed-beta policy, stored with its existing financial authorization row.

Only declared fields are editable. There is no secret/configuration key-value
store, no process-global policy mutation, and no permissive cache on DB failure.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..models import (PlatformProviderBudget, PlatformProviderCall, BetaAccessGrant,
                      TranscriptionReservation, User, AuditEvent)
from .audit import append_audit_event

PLATFORM_MODEL = "universal-3-5-pro"


class BetaPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    beta_enabled: bool = False
    platform_enabled: bool = False
    round_name: str = Field(default="Beta fechado", min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$")
    max_participants: int = Field(default=5, ge=1, le=5)
    quota_minutes: int = Field(default=600, ge=0, le=600)
    max_audio_seconds: int = Field(default=600, ge=1, le=600)
    max_upload_mb: int = Field(default=100, ge=1, le=100)
    max_stored_bytes: int = Field(default=0, ge=0, le=1099511627776)
    max_queued_per_account: int = Field(default=2, ge=1, le=100)
    max_processing_per_account: int = Field(default=1, ge=1, le=10)
    max_platform_queued: int = Field(default=10, ge=1, le=100)
    max_platform_processing: int = Field(default=1, ge=1, le=10)


def budget_row(db, *, lock=False):
    if lock and db.get_bind().dialect.name != "postgresql" and settings.APP_ENV != "test":
        raise HTTPException(503, "A configuração operacional exige PostgreSQL.")
    query = db.query(PlatformProviderBudget).filter_by(provider="assemblyai")
    return (query.with_for_update() if lock else query).populate_existing().one_or_none()


def read_policy(db, *, required=False, lock=False):
    row = budget_row(db, lock=lock)
    try:
        policy = BetaPolicy.model_validate(row.operational_policy) if row and row.operational_policy is not None else None
    except (ValidationError, TypeError, ValueError):
        raise HTTPException(503, "A configuração do Beta precisa ser revisada pelo administrador.") from None
    if required and policy is None:
        raise HTTPException(503, "A configuração do Beta ainda não foi preparada pelo administrador.")
    return row, policy


def round_policy_for_user(db, user_id):
    """Quota presentation remains readable while the round is paused."""
    row, policy = read_policy(db)
    if policy and row.round_id:
        grants = db.query(BetaAccessGrant).filter(BetaAccessGrant.user_id == user_id,
            BetaAccessGrant.round_id == row.round_id, BetaAccessGrant.revoked_at.is_(None),
            BetaAccessGrant.expires_at > datetime.now(timezone.utc)).all()
        if any("transcription.platform" in g.capabilities for g in grants):
            return policy
    return None


def initialize_policy(db, *, version, confirmed, actor_user_id):
    if not confirmed:
        raise HTTPException(422, "Confirme a preparação da configuração desativada.")
    if budget_row(db) is None:
        try:
            with db.begin_nested():
                db.add(PlatformProviderBudget(provider="assemblyai", limit_cents=0, reserved_cents=0, alert_cents=0))
                db.flush()
        except IntegrityError:
            pass
    row, policy = read_policy(db, lock=True)
    _check_version(row, version)
    if policy is not None:
        raise HTTPException(409, "A configuração já foi preparada. Recarregue a página.")
    try:
        raw = json.loads(settings.PLAN_POLICIES_JSON).get("beta", {})
        from .transcription_entitlements import PlanLimits
        limits = PlanLimits.model_validate(raw)
        if settings.AAI_BETA_ROUND_SECONDS % 60:
            raise ValueError("Round quota must use whole minutes")
        policy = BetaPolicy(max_participants=settings.AAI_BETA_MAX_USERS,
            quota_minutes=settings.AAI_BETA_ROUND_SECONDS // 60,
            max_audio_seconds=min(limits.max_audio_seconds or 600, settings.AAI_MAX_AUDIO_SECONDS),
            max_upload_mb=settings.PUBLIC_MAX_UPLOAD_MB, max_stored_bytes=limits.max_stored_bytes,
            max_queued_per_account=limits.max_queued_jobs or 2,
            max_processing_per_account=limits.max_processing_jobs or 1,
            max_platform_queued=settings.AAI_PLATFORM_MAX_QUEUED,
            max_platform_processing=settings.AAI_PLATFORM_MAX_PROCESSING)
    except (ValidationError, ValueError, TypeError, AttributeError):
        raise HTTPException(422, "Revise os valores de bootstrap da política Beta no ambiente.") from None
    # Preserve old spending and round, never import enabled flags or a new cap.
    if not row.round_id:
        row.round_id = settings.AAI_BETA_ROUND_ID.strip() or None
    row.operational_policy = policy.model_dump()
    _changed(db, row, actor_user_id, "admin.settings_initialized", {"policy": None}, {"policy": row.operational_policy})
    return row


def _check_version(row, version):
    if row.configuration_version != version:
        raise HTTPException(409, "A configuração mudou em outra aba. Recarregue antes de salvar.")


def _changed(db, row, actor, event, before, after):
    row.configuration_version += 1
    row.configuration_updated_at = datetime.now(timezone.utc)
    row.configuration_updated_by = actor
    append_audit_event(db, event=event, actor_user_id=actor, resource_type="provider",
        resource_id="assemblyai", metadata={"before": before, "after": after,
        "version": row.configuration_version, "reason": "manual_review"})
    db.flush()


def update_policy(db, *, section, changes, version, confirmed, actor_user_id):
    row, policy = read_policy(db, required=True, lock=True)
    _check_version(row, version)
    current = settings_view(db)["values"]
    changed = {key: value for key, value in changes.items() if str(current.get(key)) != str(value)}
    allowed = {key for key in POLICY_FIELDS if key.startswith(section + ".")}
    allowed |= {"beta.round_id"} if section == "beta" else set()
    allowed |= {"assemblyai.hard_stop_usd", "assemblyai.alert_usd"} if section == "assemblyai" else set()
    if set(changes) - allowed:
        raise HTTPException(422, "A configuração solicitada não pode ser editada.")
    critical = {"beta.enabled", "beta.quota_minutes_per_participant", "beta.round_id",
                "assemblyai.platform_enabled", "assemblyai.hard_stop_usd"}
    if changed.keys() & critical and not confirmed:
        raise HTTPException(422, "Confirme explicitamente a alteração operacional.")
    if not changed:
        return row
    data = policy.model_dump()
    for key, value in changed.items():
        if key in POLICY_FIELDS:
            data[POLICY_FIELDS[key]] = value
    if data["max_audio_seconds"] > min(600, settings.AAI_MAX_AUDIO_SECONDS) or data["max_upload_mb"] > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(422, "O limite solicitado excede a capacidade técnica configurada neste ambiente.")
    try:
        updated = BetaPolicy.model_validate(data)
    except ValidationError:
        raise HTTPException(422, "Confira os tipos e limites da configuração.") from None
    if updated.max_participants < row.invited_count:
        raise HTTPException(409, "O máximo não pode ficar abaixo das vagas já utilizadas nesta rodada.")
    round_id = changed.get("beta.round_id", row.round_id)
    if round_id != row.round_id:
        historical = db.query(PlatformProviderCall).count() or db.query(BetaAccessGrant).filter(BetaAccessGrant.round_id.is_not(None)).count()
        if row.invited_count or historical or row.reserved_cents > 0:
            raise HTTPException(409, "A identificação da rodada não pode mudar após convites ou uso.")
    cap = Decimal(str(changed.get("assemblyai.hard_stop_usd", row.limit_cents / 100))) * 100
    alert = Decimal(str(changed.get("assemblyai.alert_usd", row.alert_cents / 100))) * 100
    if not cap.is_finite() or not alert.is_finite() or cap < 0 or alert < 0 or cap > 100000 or alert > 100000:
        raise HTTPException(422, "Confira teto e alerta em dólares.")
    if (cap == 0 and alert != 0) or (cap > 0 and alert >= cap):
        raise HTTPException(422, "O alerta deve ser menor que o teto; com teto zero, ambos ficam em zero.")
    enabling = ((updated.beta_enabled and not policy.beta_enabled)
                or (updated.platform_enabled and not policy.platform_enabled))
    if cap > row.limit_cents or enabling:
        from .platform_budget import _valid_balance
        _valid_balance(row)
        if cap > row.balance_baseline_cents + row.balance_cents:
            raise HTTPException(409, "O teto exige conferência operacional suficiente.")
        platform_price(db, row)
    row.round_id, row.limit_cents, row.alert_cents = round_id, cap, alert
    row.operational_policy = updated.model_dump()
    _changed(db, row, actor_user_id, "admin.settings_changed",
        {key: current[key] for key in changed},
        {key: str(value) if isinstance(value, Decimal) else value for key, value in changed.items()})
    return row


def platform_price(db, row):
    from ..models import UsagePrice
    price = db.query(UsagePrice).filter_by(catalog_version=row.price_version,
        provider="assemblyai", model=PLATFORM_MODEL + "+speakers",
        metric="provider_audio_seconds", unit="second", currency="USD").one_or_none() if row.price_version else None
    if price is None or price.unit_price <= 0 or price.unit_quantity != 3600:
        raise HTTPException(503, "A tarifa desta rodada precisa de conferência operacional.")
    return price


def _definition(key, kind, description, default, *, minimum=None, maximum=None, editable=True, confirmation=False, options=None):
    return {"key": key, "type": kind, "description": description, "default": default,
        "minimum": minimum, "maximum": maximum, "editable": editable,
        "requires_confirmation": confirmation, "runtime": editable, "sensitive": False,
        "options": options}


POLICY_FIELDS = {
    "beta.enabled": "beta_enabled", "beta.round_name": "round_name",
    "beta.max_participants": "max_participants", "beta.quota_minutes_per_participant": "quota_minutes",
    "assemblyai.platform_enabled": "platform_enabled",
    "limits.max_audio_seconds": "max_audio_seconds", "limits.max_upload_mb": "max_upload_mb",
    "limits.max_stored_bytes": "max_stored_bytes", "limits.max_queued_per_account": "max_queued_per_account",
    "limits.max_processing_per_account": "max_processing_per_account",
    "limits.max_platform_queued": "max_platform_queued", "limits.max_platform_processing": "max_platform_processing",
}


def settings_view(db):
    row, policy = read_policy(db)
    effective = policy or BetaPolicy()
    values = {key: getattr(effective, field) for key, field in POLICY_FIELDS.items()}
    values.update({"beta.round_id": row.round_id if row else "",
        "assemblyai.hard_stop_usd": format((row.limit_cents / 100).normalize(), "f") if row else "0",
        "assemblyai.alert_usd": format((row.alert_cents / 100).normalize(), "f") if row else "0",
        "assemblyai.model": PLATFORM_MODEL, "assemblyai.speaker_detection": True,
        "assemblyai.price_version": row.price_version if row else None})
    saved_values = dict(values)
    values["limits.max_audio_seconds"] = min(effective.max_audio_seconds, settings.AAI_MAX_AUDIO_SECONDS)
    values["limits.max_upload_mb"] = min(effective.max_upload_mb, settings.MAX_UPLOAD_SIZE_MB)
    overrides = {key: "Limitado pela capacidade técnica do ambiente; exceções individuais continuam preservadas."
        for key in values if values[key] != saved_values[key]}
    definitions = []
    descriptions = {"beta_enabled": "Autoriza novas operações da rodada.", "platform_enabled": "Autoriza uso da credencial da USAGI.",
        "round_name": "Nome de apresentação da rodada.", "quota_minutes": "Minutos por conta na rodada, sem renovação.",
        "max_participants": "Contas distintas na rodada; vagas não são repostas.",
        "max_audio_seconds": "Duração máxima por arquivo da rodada.", "max_upload_mb": "Tamanho padrão por arquivo; exceções individuais permanecem.",
        "max_stored_bytes": "Armazenamento de áudio por conta na rodada.", "max_queued_per_account": "Transcrições aguardando por conta.",
        "max_processing_per_account": "Processamentos simultâneos por conta.", "max_platform_queued": "Chamadas da plataforma aguardando.",
        "max_platform_processing": "Chamadas simultâneas da plataforma."}
    for key, field in POLICY_FIELDS.items():
        f = BetaPolicy.model_fields[field]
        schema = BetaPolicy.model_json_schema()["properties"][field]
        definitions.append(_definition(key, schema["type"], descriptions[field], f.default,
            minimum=schema.get("minimum"), maximum=schema.get("maximum"),
            confirmation=field in {"beta_enabled", "platform_enabled", "quota_minutes"}))
        if key in {"limits.max_audio_seconds", "limits.max_upload_mb"}:
            definitions[-1]["maximum"] = min(definitions[-1]["maximum"],
                settings.AAI_MAX_AUDIO_SECONDS if key == "limits.max_audio_seconds" else settings.MAX_UPLOAD_SIZE_MB)
    definitions += [_definition("beta.round_id", "string", "Identificador imutável após o primeiro convite ou uso.", ""),
        _definition("assemblyai.hard_stop_usd", "decimal", "Teto interno cumulativo; não é saldo externo.", "0", minimum="0", maximum="1000", confirmation=True),
        _definition("assemblyai.alert_usd", "decimal", "Alerta de revisão operacional, abaixo do teto.", "0", minimum="0", maximum="1000"),
        _definition("assemblyai.model", "enum", "Configuração fixa para esta rodada Beta.", PLATFORM_MODEL, editable=False, options=[PLATFORM_MODEL]),
        _definition("assemblyai.speaker_detection", "boolean", "Configuração fixa para esta rodada Beta.", True, editable=False),
        _definition("assemblyai.price_version", "string", "Versão de tarifa conferida pelo operador.", None, editable=False)]
    definitions[len(POLICY_FIELDS)]["editable"] = not (row and (row.invited_count or
        db.query(PlatformProviderCall).count() or db.query(BetaAccessGrant).filter(BetaAccessGrant.round_id.is_not(None)).count()))
    definitions[len(POLICY_FIELDS)]["requires_confirmation"] = True
    return {"configured": policy is not None, "version": row.configuration_version if row else 0,
        "values": values, "saved_values": saved_values, "overrides": overrides, "definitions": definitions,
        "updated_at": row.configuration_updated_at if row else None}


def participants_view(db):
    row, policy = read_policy(db)
    if not policy or not row.round_id:
        return {"items": [], "used_slots": row.invited_count if row else 0, "maximum": (policy or BetaPolicy()).max_participants}
    from .transcription_entitlements import HELD, _aware
    grants = db.query(BetaAccessGrant).filter_by(round_id=row.round_id).order_by(BetaAccessGrant.expires_at.desc()).all()
    platform_grants = [g for g in grants if "transcription.platform" in g.capabilities]
    user_ids = {g.user_id for g in platform_grants}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    holds = db.query(TranscriptionReservation).filter_by(round_id=row.round_id, source="usagi").all()
    items = []
    for user_id in sorted(user_ids):
        user = users.get(user_id)
        if user is None:
            continue  # Erasure retains the anonymous durable invitation count.
        own = [g for g in platform_grants if g.user_id == user_id]
        active = next((g for g in own if g.revoked_at is None and _aware(g.expires_at) > datetime.now(timezone.utc)), None)
        grant = active or own[0]
        used = sum((r.reserved_seconds for r in holds if r.user_id == user_id and r.state == "consumed"), Decimal(0))
        pending = sum((r.reserved_seconds for r in holds if r.user_id == user_id and r.state in HELD), Decimal(0))
        limit = policy.quota_minutes * 60
        items.append({"user_id": user_id, "username": user.username, "email": user.email,
            "grant_id": grant.id, "active": active is not None, "expires_at": grant.expires_at,
            "revoked_at": grant.revoked_at, "capabilities": grant.capabilities,
            "quota_seconds": limit, "consumed_seconds": str(used), "reserved_seconds": str(pending),
            "available_seconds": str(max(Decimal(0), limit - used - pending)),
            "committed_above_limit": used + pending > limit})
    return {"items": items, "used_slots": max(row.invited_count, len(user_ids)), "maximum": policy.max_participants}


def overview(db):
    """Explicit projection: no provider balance, references or credential values."""
    row, policy = read_policy(db)
    participants = participants_view(db)
    calls = db.query(PlatformProviderCall).filter_by(provider="assemblyai").all()
    committed = row.reserved_cents if row else Decimal(0)
    cap = row.limit_cents if row else Decimal(0)
    holds = db.query(TranscriptionReservation).filter_by(round_id=row.round_id, source="usagi").all() if row and row.round_id else []
    from .transcription_entitlements import HELD
    from .platform_budget import _valid_balance
    balance_review_valid = price_review_valid = False
    if row:
        try:
            _valid_balance(row)
            balance_review_valid = True
        except HTTPException:
            pass
        try:
            platform_price(db, row)
            price_review_valid = True
        except HTTPException:
            pass
    return {"participants_used": participants["used_slots"], "participants_maximum": participants["maximum"],
        "consumed_seconds": str(sum((r.reserved_seconds for r in holds if r.state == "consumed"), Decimal(0))),
        "reserved_seconds": str(sum((r.reserved_seconds for r in holds if r.state in HELD), Decimal(0))),
        "financial": {"authorized_usd": str(committed / 100), "available_usd": str(max(Decimal(0), cap - committed) / 100),
            "committed_above_limit": committed > cap, "alert_reached": bool(row and row.alert_cents > 0 and committed >= row.alert_cents),
            "review_required": bool(row and row.review_required), "balance_review_valid": balance_review_valid,
            "price_review_valid": price_review_valid,
            "unresolved_calls": sum(c.state == "attempted" and c.settled_at is None and c.released_at is None for c in calls),
            "queued_calls": sum(c.state == "reserved" and c.released_at is None for c in calls)},
        "system": {"database": "connected", "assemblyai_credential_configured": bool(settings.AAI_API_KEY_CONFIGURED or settings.AAI_API_KEY),
            "firebase_configured": bool(settings.FIREBASE_AUTH_ENABLED and settings.FIREBASE_PROJECT_ID)}}


def settings_history(db):
    rows = db.query(AuditEvent).filter(AuditEvent.event.in_(["admin.settings_initialized", "admin.settings_changed"])).order_by(AuditEvent.id.desc()).limit(20).all()
    return {"items": [{"id": row.id, "event": row.event, "actor_user_id": row.actor_user_id,
        "created_at": row.timestamp, "changes": row.event_metadata} for row in rows]}
