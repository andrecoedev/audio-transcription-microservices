"""Conservative cumulative USD holds, independent of best-effort metering.

No automatic refund (including deletion/timeout), and no automatic second call.
Admission owner commits; the Worker commits its marker before any HTTP request.
"""
from decimal import Decimal, ROUND_CEILING
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..models import IntelligencePlatformCall, MeetingIntelligence, PlatformProviderBudget, TranscriptionOwnership
from .transcription_entitlements import access, require_execution


def require_groq_configuration(*, worker=False):
    if not (settings.GROQ_PLATFORM_ENABLED and settings.GROQ_PLATFORM_BUDGET_CENTS > 0
            and settings.GROQ_MAX_ACTIVE_PER_USER > 0 and settings.GROQ_MAX_PROCESSING_PER_USER > 0
            and settings.GROQ_INPUT_USD_PER_MILLION > 0 and settings.GROQ_OUTPUT_USD_PER_MILLION > 0
            and (bool(settings.GROQ_API_KEY) if worker else settings.GROQ_API_KEY_CONFIGURED)):
        raise HTTPException(503, "Groq está indisponível. Consulte o administrador ou escolha outro serviço de resumo.")


def reservation_cents(input_bound, output_limit):
    # Bounds include prompt/schema/envelope and all generated tokens, including
    # hidden reasoning. Rates are operator-reviewed ceilings, not invoice data.
    cost = (Decimal(input_bound) * settings.GROQ_INPUT_USD_PER_MILLION
            + Decimal(output_limit) * settings.GROQ_OUTPUT_USD_PER_MILLION) / Decimal(1000000)
    return max(1, int((cost * 100).to_integral_value(rounding=ROUND_CEILING)))


def has_headroom(db):
    require_groq_configuration()
    budget = db.get(PlatformProviderBudget, "groq")
    used = budget.reserved_cents if budget else 0
    limit = min(budget.limit_cents, settings.GROQ_PLATFORM_BUDGET_CENTS) if budget else settings.GROQ_PLATFORM_BUDGET_CENTS
    return used + reservation_cents(settings.GROQ_MAX_INPUT_TOKENS, settings.GROQ_MAX_OUTPUT_TOKENS) <= limit


def _running(db, user_id, states, exclude_id=None):
    query = db.query(MeetingIntelligence).join(TranscriptionOwnership,
        TranscriptionOwnership.transcription_id == MeetingIntelligence.meeting_id).filter(
        TranscriptionOwnership.user_id == user_id, MeetingIntelligence.provider == "groq",
        MeetingIntelligence.status.in_(states))
    return query.filter(MeetingIntelligence.id != exclude_id).count() if exclude_id else query.count()


def reserve_groq_call(db, user_id, intelligence_id, context):
    require_groq_configuration()
    access(db, user_id, lock=True)
    require_execution(db, user_id, "groq", "platform")
    existing = db.query(IntelligencePlatformCall).filter_by(intelligence_id=intelligence_id).one_or_none()
    if existing:
        if existing.user_id != user_id:
            raise HTTPException(403, "A operação pertence a outra conta.")
        return existing
    if _running(db, user_id, {"pending", "processing"}, intelligence_id) >= settings.GROQ_MAX_ACTIVE_PER_USER:
        raise HTTPException(429, "Aguarde um resumo terminar antes de solicitar outro.")
    from .groq_intelligence import prepared_request
    try:
        _, bound = prepared_request(context, settings.GROQ_MODEL)
    except ValueError:
        raise HTTPException(422, "Esta reunião excede o limite do serviço de resumo. Escolha outro serviço ou reduza o conteúdo.") from None
    output = settings.GROQ_MAX_OUTPUT_TOKENS
    amount = reservation_cents(bound, output)
    if db.get(PlatformProviderBudget, "groq") is None:
        try:
            with db.begin_nested():
                db.add(PlatformProviderBudget(provider="groq", limit_cents=settings.GROQ_PLATFORM_BUDGET_CENTS, reserved_cents=0))
                db.flush()
        except IntegrityError:
            pass  # Concurrent creator; the conditional UPDATE is authoritative.
    updated = db.query(PlatformProviderBudget).filter(
        PlatformProviderBudget.provider == "groq",
        PlatformProviderBudget.reserved_cents + amount <= PlatformProviderBudget.limit_cents,
        PlatformProviderBudget.reserved_cents + amount <= settings.GROQ_PLATFORM_BUDGET_CENTS).update(
        {PlatformProviderBudget.reserved_cents: PlatformProviderBudget.reserved_cents + amount}, synchronize_session=False)
    if updated != 1:
        raise HTTPException(429, "O limite de uso do serviço foi atingido. Escolha outro serviço ou contate o administrador.")
    call = IntelligencePlatformCall(id=str(uuid4()), intelligence_id=intelligence_id, user_id=user_id,
        provider="groq", model=settings.GROQ_MODEL, input_token_bound=bound, output_token_limit=output,
        reserved_cents=amount, state="reserved")
    db.add(call)
    db.flush()
    return call


def authorize_groq_claim(db, user_id, intelligence_id):
    require_groq_configuration(worker=True)
    access(db, user_id, lock=True)
    require_execution(db, user_id, "groq", "platform")
    if _running(db, user_id, {"processing"}, intelligence_id) >= settings.GROQ_MAX_PROCESSING_PER_USER:
        raise HTTPException(429, "O limite de resumos simultâneos foi atingido.")


def begin_groq_call(db, intelligence_id, user_id, context, model):
    require_groq_configuration(worker=True)
    access(db, user_id, lock=True)
    require_execution(db, user_id, "groq", "platform")
    budget = db.get(PlatformProviderBudget, "groq")
    if not budget or budget.reserved_cents > min(budget.limit_cents, settings.GROQ_PLATFORM_BUDGET_CENTS):
        raise RuntimeError("Groq budget policy changed before inference")
    call = db.query(IntelligencePlatformCall).filter_by(intelligence_id=intelligence_id).one_or_none()
    if not call or call.user_id != user_id or call.model != model or call.provider != "groq":
        raise RuntimeError("Groq call has no matching authorization")
    from .groq_intelligence import prepared_request
    _, bound = prepared_request(context, model)
    # A policy change cannot increase the original call allowance or lower the
    # conservative cost protection underneath an admitted request.
    if bound > call.input_token_bound or settings.GROQ_MAX_OUTPUT_TOKENS > call.output_token_limit or reservation_cents(bound, settings.GROQ_MAX_OUTPUT_TOKENS) > call.reserved_cents:
        raise RuntimeError("Groq configuration exceeds authorized reservation")
    updated = db.query(IntelligencePlatformCall).filter_by(id=call.id, state="reserved").update(
        {IntelligencePlatformCall.state: "attempted"}, synchronize_session=False)
    if updated != 1:
        raise RuntimeError("Groq call cannot be repeated automatically")
    db.commit()
