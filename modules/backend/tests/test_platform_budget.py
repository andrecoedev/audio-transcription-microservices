from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from src.models import (
    GuestSession,
    PlatformProviderBudget,
    PlatformProviderCall,
    Transcription,
    TranscriptionOwnership,
)
from src.services import platform_budget
from src.services.platform_budget import begin_platform_call, reserve_platform_call


def _transcription(db, filename="budget-test.wav"):
    row = Transcription(
        filename=filename,
        original_filename=filename,
        file_size_mb=0.1,
        duration_seconds=600,
        transcription_model="assemblyai",
        status="queued",
    )
    db.add(row)
    db.flush()
    return row


def _enable_budget(monkeypatch, *, limit=200, max_seconds=600):
    monkeypatch.setattr(platform_budget.settings, "AAI_PLATFORM_ENABLED", True)
    monkeypatch.setattr(platform_budget.settings, "AAI_PLATFORM_BUDGET_CENTS", limit)
    monkeypatch.setattr(platform_budget.settings, "AAI_MAX_AUDIO_SECONDS", max_seconds)


def test_reservation_uses_rounded_worst_case_and_enforces_cumulative_cap(
    db_context, monkeypatch
):
    _enable_budget(monkeypatch, limit=200, max_seconds=600)
    db = db_context["session_factory"]()
    first = _transcription(db, "first.wav")
    second = _transcription(db, "second.wav")
    reserve_platform_call(db, first.id, "guest")
    db.commit()

    budget = db.get(PlatformProviderBudget, "assemblyai")
    call = db.query(PlatformProviderCall).filter_by(transcription_id=first.id).one()
    assert budget.limit_cents == 200
    assert budget.reserved_cents == 17
    assert call.reserved_cents == 17
    assert call.context == "guest"

    monkeypatch.setattr(platform_budget.settings, "AAI_PLATFORM_BUDGET_CENTS", 17)
    with pytest.raises(HTTPException) as error:
        reserve_platform_call(db, second.id, "local")
    assert error.value.status_code == 429
    db.refresh(budget)
    assert budget.reserved_cents == 17
    assert db.query(PlatformProviderCall).filter_by(transcription_id=second.id).count() == 0
    db.close()


def test_platform_call_attempt_marker_commits_once_and_prevents_repeat(
    db_context, monkeypatch
):
    _enable_budget(monkeypatch)
    db = db_context["session_factory"]()
    transcription = _transcription(db)
    reserve_platform_call(db, transcription.id, "local")
    db.commit()

    assert begin_platform_call(db, transcription.id) == "local"
    call = db.query(PlatformProviderCall).filter_by(transcription_id=transcription.id).one()
    assert call.state == "attempted"
    with pytest.raises(RuntimeError, match="cannot be repeated"):
        begin_platform_call(db, transcription.id)
    db.close()


def test_deletion_keeps_reservation_and_provider_call_with_null_transcription(
    db_context, monkeypatch
):
    _enable_budget(monkeypatch)
    db = db_context["session_factory"]()
    transcription = _transcription(db)
    transcription_id = transcription.id
    reserve_platform_call(db, transcription_id, "guest")
    db.commit()

    db.delete(db.get(Transcription, transcription_id))
    db.commit()

    call = db.query(PlatformProviderCall).one()
    budget = db.get(PlatformProviderBudget, "assemblyai")
    assert call.transcription_id is None
    assert call.reserved_cents == 17
    assert budget.reserved_cents == 17
    db.close()


def test_reserved_context_survives_ownership_transfer(db_context, monkeypatch):
    _enable_budget(monkeypatch)
    db = db_context["session_factory"]()
    guest = GuestSession(
        id="00000000-0000-0000-0000-000000000001",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    transcription = _transcription(db)
    ownership = TranscriptionOwnership(
        transcription_id=transcription.id,
        owner_sub="guest",
        guest_session_id=guest.id,
    )
    db.add_all([guest, ownership])
    db.flush()
    reserve_platform_call(db, transcription.id, "guest")
    db.commit()

    ownership.owner_sub = "1"
    ownership.user_id = 1
    ownership.guest_session_id = None
    db.commit()

    call = db.query(PlatformProviderCall).filter_by(transcription_id=transcription.id).one()
    assert call.context == "guest"
    assert begin_platform_call(db, transcription.id) == "guest"
    db.close()


def test_attempt_without_reservation_is_rejected(db_context, monkeypatch):
    _enable_budget(monkeypatch)
    db = db_context["session_factory"]()
    transcription = _transcription(db)

    with pytest.raises(RuntimeError, match="no authorized reservation"):
        begin_platform_call(db, transcription.id)
    db.close()
