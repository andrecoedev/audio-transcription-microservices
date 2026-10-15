"""Transactional authorization, not an invoice or automatic balance reader.

The existing budget row serializes admission across Workers. Holds and manual
evidence survive restarts/deletion. Never hold a transaction during network I/O.
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..models import BetaAccessGrant, PlatformProviderBudget, PlatformProviderCall, UsagePrice
from .audit import append_audit_event

logger = logging.getLogger(__name__)
UNAVAILABLE = "Este recurso está temporariamente indisponível no Beta."
PRECISION = Decimal("0.00000001")
REFERENCE = re.compile(r"[a-z][a-z0-9_.:-]{0,63}\Z")
REMOTE_ID = re.compile(r"(?=.{1,128}$)[A-Za-z0-9-]+\Z")


def now_utc():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _policy(*, enabled=True):
    references = (settings.AAI_BETA_ROUND_ID, settings.AAI_PLATFORM_PRICE_VERSION,
                  settings.AAI_PLATFORM_KEY_REFERENCE, settings.AAI_PLATFORM_PROJECT_REFERENCE)
    if ((enabled and not settings.AAI_PLATFORM_ENABLED)
        or settings.AAI_PLATFORM_BUDGET_CENTS <= 0 or settings.AAI_PLATFORM_HOURLY_USD <= 0
        or not all(REFERENCE.fullmatch(ref) for ref in references)
        or settings.AAI_PLATFORM_ALERT_CENTS > settings.AAI_PLATFORM_BUDGET_CENTS):
        raise HTTPException(503, UNAVAILABLE)


def _budget(db, *, create=False, lock=False):
    if lock and db.get_bind().dialect.name != "postgresql" and settings.APP_ENV != "test":
        raise HTTPException(503, UNAVAILABLE)
    if create and db.get(PlatformProviderBudget, "assemblyai") is None:
        try:
            with db.begin_nested():
                db.add(PlatformProviderBudget(provider="assemblyai",
                    limit_cents=settings.AAI_PLATFORM_BUDGET_CENTS, reserved_cents=0,
                    alert_cents=settings.AAI_PLATFORM_ALERT_CENTS, round_id=settings.AAI_BETA_ROUND_ID))
                db.flush()
        except IntegrityError:
            pass
    query = db.query(PlatformProviderBudget).filter_by(provider="assemblyai")
    return (query.with_for_update() if lock else query).populate_existing().one_or_none()


def _valid_balance(budget):
    if (budget is None or budget.review_required or not budget.balance_exclusive
        or budget.round_id != settings.AAI_BETA_ROUND_ID
        or budget.key_reference != settings.AAI_PLATFORM_KEY_REFERENCE
        or budget.project_reference != settings.AAI_PLATFORM_PROJECT_REFERENCE
        or budget.balance_cents is None or budget.balance_baseline_cents is None
        or budget.balance_checked_at is None
        or not now_utc() - timedelta(hours=settings.AAI_BALANCE_REVIEW_HOURS)
            <= aware(budget.balance_checked_at) <= now_utc() + timedelta(minutes=1)):
        raise HTTPException(503, UNAVAILABLE)


def _ceiling(budget):
    _valid_balance(budget)
    return min(Decimal(budget.limit_cents), Decimal(settings.AAI_PLATFORM_BUDGET_CENTS),
               budget.balance_baseline_cents + budget.balance_cents)


def _amount(seconds, hourly_rate_cents):
    seconds = Decimal(str(seconds))
    if not seconds.is_finite() or seconds <= 0 or seconds > settings.AAI_MAX_AUDIO_SECONDS:
        raise HTTPException(422, "Não foi possível verificar a duração permitida do áudio.")
    return (seconds.to_integral_value(rounding=ROUND_CEILING) * hourly_rate_cents
            / Decimal(3600)).quantize(PRECISION, rounding=ROUND_CEILING)


def platform_reservation_amount_cents(duration_seconds=None):
    return _amount(duration_seconds or settings.AAI_MAX_AUDIO_SECONDS,
                   settings.AAI_PLATFORM_HOURLY_USD * 100)


def platform_budget_has_headroom(db):
    try:
        _policy()
        budget = _budget(db)
        ceiling = _ceiling(budget)
        return budget.reserved_cents + platform_reservation_amount_cents() <= ceiling
    except HTTPException:
        return False


def lock_beta_enrollment(db, round_id, user_id):
    """Called after locking the target User, before adding a platform grant."""
    _policy(enabled=False)
    budget = _budget(db, create=True, lock=True)
    if round_id != settings.AAI_BETA_ROUND_ID or budget.round_id != round_id:
        raise HTTPException(409, "A rodada Beta precisa ser configurada pelo operador.")
    active = db.query(BetaAccessGrant).filter(BetaAccessGrant.round_id == round_id,
        BetaAccessGrant.revoked_at.is_(None), BetaAccessGrant.expires_at > now_utc()).all()
    invited = {g.user_id for g in active if "transcription.platform" in g.capabilities}
    if user_id not in invited and len(invited) >= settings.AAI_BETA_MAX_USERS:
        raise HTTPException(409, "O limite de convidados desta rodada foi atingido.")


def reserve_platform_call(db, transcription_id, context, *, duration_seconds=None):
    _policy()
    budget = _budget(db, lock=True)
    ceiling = _ceiling(budget)
    existing = db.query(PlatformProviderCall).filter_by(transcription_id=transcription_id).one_or_none()
    if existing:
        if existing.released_at or existing.state != "reserved":
            raise HTTPException(409, UNAVAILABLE)
        return existing
    queued = db.query(PlatformProviderCall).filter_by(provider="assemblyai", state="reserved",
        released_at=None).count()
    if queued >= settings.AAI_PLATFORM_MAX_QUEUED:
        raise HTTPException(429, UNAVAILABLE)
    amount = platform_reservation_amount_cents(duration_seconds)
    if budget.reserved_cents + amount > ceiling:
        raise HTTPException(429, UNAVAILABLE)
    budget.reserved_cents += amount
    call = PlatformProviderCall(transcription_id=transcription_id, operation_key=f"transcription:{transcription_id}",
        provider="assemblyai", context=context,
        credential_source="platform", reserved_cents=amount, round_id=budget.round_id,
        model=settings.AAI_PLATFORM_MODEL, use_diarization=True,
        price_version=settings.AAI_PLATFORM_PRICE_VERSION,
        hourly_rate_cents=settings.AAI_PLATFORM_HOURLY_USD * 100)
    db.add(call)
    db.flush()
    return call


def begin_platform_call(db, transcription_id, *, duration_seconds=None):
    original = db.query(PlatformProviderCall).filter_by(transcription_id=transcription_id).one_or_none()
    if original is None or original.context == "guest":
        raise HTTPException(403, UNAVAILABLE)
    _policy()
    budget = _budget(db, lock=True)
    ceiling = _ceiling(budget)
    call = db.query(PlatformProviderCall).filter_by(transcription_id=transcription_id).populate_existing().one_or_none()
    if not call or call.context == "guest" or call.credential_source != "platform":
        raise HTTPException(403, UNAVAILABLE)
    if call.state != "reserved" or call.released_at:
        raise HTTPException(409, UNAVAILABLE)
    if (call.round_id != budget.round_id or call.model != settings.AAI_PLATFORM_MODEL
        or call.price_version != settings.AAI_PLATFORM_PRICE_VERSION
        or call.hourly_rate_cents != settings.AAI_PLATFORM_HOURLY_USD * 100):
        raise HTTPException(503, UNAVAILABLE)
    amount = _amount(duration_seconds or settings.AAI_MAX_AUDIO_SECONDS, call.hourly_rate_cents)
    if amount > call.reserved_cents:
        raise HTTPException(429, UNAVAILABLE)
    revised_total = budget.reserved_cents - call.reserved_cents + amount
    if revised_total > ceiling:
        raise HTTPException(429, UNAVAILABLE)
    active = db.query(PlatformProviderCall).filter_by(provider="assemblyai", state="attempted",
        settled_at=None, released_at=None).count()
    if active >= settings.AAI_PLATFORM_MAX_PROCESSING:
        raise HTTPException(429, UNAVAILABLE)
    budget.reserved_cents = revised_total
    call.reserved_cents = amount
    call.state = "attempted"
    db.flush()
    committed = sum((c.reserved_cents for c in db.query(PlatformProviderCall).filter_by(
        provider="assemblyai", state="attempted", released_at=None)), Decimal(0))
    threshold = min(budget.alert_cents, Decimal(settings.AAI_PLATFORM_ALERT_CENTS))
    if threshold > 0 and committed >= threshold and budget.alerted_at is None:
        budget.alerted_at = now_utc()
        append_audit_event(db, event="provider.budget_alert", actor_type="system",
            resource_type="provider", resource_id="assemblyai")
        logger.warning("AssemblyAI platform usage reached its operational review threshold")
    db.commit()
    return call.context


def observe_platform_call(db, transcription_id, event, *, call_id=None):
    """Critical persistence; exceptions abort polling, never authorize a retry."""
    budget = _budget(db, lock=True)
    query = db.query(PlatformProviderCall)
    call = (query.filter_by(id=call_id) if call_id is not None else
            query.filter_by(transcription_id=transcription_id)).one_or_none()
    if not call or call.state != "attempted":
        raise RuntimeError("Provider observation has no live authorization")
    remote_id = event.get("provider_id")
    if not isinstance(remote_id, str) or not REMOTE_ID.fullmatch(remote_id):
        raise RuntimeError("Invalid remote transcript reference")
    if call.remote_transcript_id and call.remote_transcript_id != remote_id:
        raise RuntimeError("Remote transcript reference changed")
    call.remote_transcript_id = remote_id
    status = event.get("status")
    if status not in {"queued", "processing", "completed", "error", "unknown"}:
        raise RuntimeError("Invalid remote transcript status")
    if call.settled_at:
        if status != call.provider_status:
            raise RuntimeError("Remote terminal state changed")
        return
    if call.released_at:
        raise RuntimeError("Provider observation has released authorization")
    call.provider_status = status
    duration = event.get("audio_duration_seconds")
    if duration is not None:
        number = Decimal(str(duration))
        if not number.is_finite() or number < 0 or number > Decimal("1e12"):
            raise RuntimeError("Invalid provider duration")
        call.provider_audio_seconds = number
        if status == "completed":
            call.estimated_cost_cents = (number * call.hourly_rate_cents / 3600).quantize(PRECISION, rounding=ROUND_CEILING)
            if call.estimated_cost_cents > call.reserved_cents:
                budget.review_required = True
    if status in {"completed", "error"}:
        call.settled_at = now_utc()
        if status == "error":
            call.released_at = now_utc()
            budget.reserved_cents -= call.reserved_cents
    db.flush()


def release_unattempted_call(db, transcription_id):
    budget = _budget(db, lock=True)
    call = db.query(PlatformProviderCall).filter_by(transcription_id=transcription_id).one_or_none()
    if call and call.state == "reserved" and call.released_at is None and call.model is not None:
        budget.reserved_cents -= call.reserved_cents
        call.released_at = now_utc()
        db.flush()


def record_balance_check(db, *, available_usd, checked_at, key_reference, project_reference,
                         exclusive, actor_user_id):
    _policy(enabled=False)
    budget = _budget(db, create=True, lock=True)
    amount = Decimal(available_usd)
    if (not amount.is_finite() or amount < 0 or checked_at.tzinfo is None
        or not now_utc() - timedelta(hours=settings.AAI_BALANCE_REVIEW_HOURS)
            <= checked_at <= now_utc() + timedelta(minutes=1)
        or not all(REFERENCE.fullmatch(ref) for ref in (key_reference, project_reference))):
        raise HTTPException(422, "Confira saldo, horário e referências operacionais não secretas.")
    if (key_reference != settings.AAI_PLATFORM_KEY_REFERENCE
        or project_reference != settings.AAI_PLATFORM_PROJECT_REFERENCE
        or budget.round_id != settings.AAI_BETA_ROUND_ID):
        raise HTTPException(409, "As referências operacionais não correspondem à configuração.")
    pending = db.query(PlatformProviderCall).filter_by(provider="assemblyai", settled_at=None,
        released_at=None).count()
    if pending and exclusive:
        raise HTTPException(409, "Concilie os processamentos pendentes antes de confirmar o saldo.")
    if not exclusive:
        budget.balance_exclusive = False
        append_audit_event(db, event="provider.balance_checked", actor_user_id=actor_user_id,
            resource_type="provider", resource_id="assemblyai", metadata={
                "exclusive": False, "checked_at": checked_at.isoformat(),
                "key_reference": key_reference, "project_reference": project_reference})
        db.flush()
        return budget
    budget.balance_cents = amount * 100
    budget.balance_baseline_cents = budget.reserved_cents
    budget.balance_checked_at = checked_at
    budget.balance_exclusive = exclusive
    budget.key_reference, budget.project_reference = key_reference, project_reference
    budget.review_required = False
    # Explicit operator configuration supplies the price; no hardcoded tariff.
    # Requiring quiescence prevents a new price from repricing an in-flight call.
    model = settings.AAI_PLATFORM_MODEL + "+speakers"
    price = db.query(UsagePrice).filter_by(catalog_version=settings.AAI_PLATFORM_PRICE_VERSION,
        provider="assemblyai", model=model, metric="provider_audio_seconds", unit="second").one_or_none()
    if price and (price.currency != "USD" or price.unit_price != settings.AAI_PLATFORM_HOURLY_USD
                  or price.unit_quantity != 3600):
        raise HTTPException(409, "Use uma nova versão de tarifa; o histórico não pode ser reescrito.")
    if price is None:
        db.add(UsagePrice(id=str(uuid4()), catalog_version=settings.AAI_PLATFORM_PRICE_VERSION,
            provider="assemblyai", model=model, metric="provider_audio_seconds", unit="second",
            currency="USD", unit_price=settings.AAI_PLATFORM_HOURLY_USD, unit_quantity=3600,
            effective_from=checked_at, source="https://www.assemblyai.com/pricing"))
    append_audit_event(db, event="provider.balance_checked", actor_user_id=actor_user_id,
        resource_type="provider", resource_id="assemblyai", metadata={
            "available_usd": str(amount), "checked_at": checked_at.isoformat(), "exclusive": exclusive,
            "key_reference": key_reference, "project_reference": project_reference,
            "authorized_cents": str(budget.reserved_cents)})
    db.flush()
    return budget
