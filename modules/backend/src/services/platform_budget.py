"""Conservative cumulative AssemblyAI admission, independent of ownership/RQ.

Reserve a full maximum-length request at $1/hour (above the reviewed $0.17/hour
Universal-2+speakers rate). Never refund ambiguous attempts, retry POSTs, or reset
on deletion. This bounds authorized calls, not the provider's actual invoice.
"""

import math

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..models import PlatformProviderBudget, PlatformProviderCall


def reserve_platform_call(db, transcription_id: int, context: str) -> None:
    if not settings.AAI_PLATFORM_ENABLED or settings.AAI_PLATFORM_BUDGET_CENTS <= 0:
        raise HTTPException(503, "Platform transcription is unavailable")
    # Worst case includes silence and rounded-up cents; mono WAV only, no add-ons
    # beyond speaker detection, fixed model. Budget is shared by all platform use.
    amount = math.ceil(settings.AAI_MAX_AUDIO_SECONDS * 100 / 3600)
    budget = db.get(PlatformProviderBudget, "assemblyai")
    if budget is None:
        try:
            with db.begin_nested():
                db.add(PlatformProviderBudget(provider="assemblyai",
                    limit_cents=settings.AAI_PLATFORM_BUDGET_CENTS, reserved_cents=0))
                db.flush()
        except IntegrityError:
            # Another request created the singleton. No partial reservation.
            pass
    updated = db.query(PlatformProviderBudget).filter(
        PlatformProviderBudget.provider == "assemblyai",
        PlatformProviderBudget.reserved_cents + amount <= PlatformProviderBudget.limit_cents,
        PlatformProviderBudget.reserved_cents + amount <= settings.AAI_PLATFORM_BUDGET_CENTS,
    ).update({PlatformProviderBudget.reserved_cents: PlatformProviderBudget.reserved_cents + amount},
             synchronize_session=False)
    if updated != 1:
        raise HTTPException(429, "Platform transcription budget exhausted")
    db.add(PlatformProviderCall(transcription_id=transcription_id, provider="assemblyai",
        context=context, credential_source="platform", reserved_cents=amount))
    db.flush()


def begin_platform_call(db, transcription_id: int) -> str:
    """Commit the no-repeat marker BEFORE upload/submit, including crash windows."""
    call = db.query(PlatformProviderCall).filter_by(transcription_id=transcription_id).one_or_none()
    if not call or call.credential_source != "platform" or call.provider != "assemblyai":
        raise RuntimeError("Platform call has no authorized reservation")
    if not settings.AAI_PLATFORM_ENABLED:
        raise RuntimeError("Platform transcription is disabled")
    updated = db.query(PlatformProviderCall).filter(
        PlatformProviderCall.id == call.id, PlatformProviderCall.state == "reserved",
    ).update({PlatformProviderCall.state: "attempted"}, synchronize_session=False)
    if updated != 1:
        raise RuntimeError("Platform call cannot be repeated automatically")
    context = call.context
    db.commit()
    return context
