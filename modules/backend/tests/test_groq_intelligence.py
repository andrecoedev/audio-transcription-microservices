"""Runtime regressions for the explicitly selected, platform funded Groq path."""

import copy
import json
from decimal import Decimal
import pytest
from rq.exceptions import NoSuchJobError

from src.config import settings
from src.models import (
    BetaAccessGrant, IntelligencePlatformCall, MeetingIntelligence,
    PlatformProviderBudget, UsageEvent, UserProviderPreferences,
)
from src.services.transcription_entitlements import CAPABILITIES, now_utc
from src.workers import meeting_intelligence_worker as worker
from .test_meeting_intelligence import seed_meeting, valid_result


def _configure(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_PLATFORM_ENABLED", True)
    monkeypatch.setattr(settings, "GROQ_API_KEY_CONFIGURED", True)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "synthetic-runtime-key")
    monkeypatch.setattr(settings, "GROQ_PLATFORM_BUDGET_CENTS", 100)
    monkeypatch.setattr(settings, "GROQ_INPUT_USD_PER_MILLION", Decimal("1"))
    monkeypatch.setattr(settings, "GROQ_OUTPUT_USD_PER_MILLION", Decimal("1"))
    monkeypatch.setattr(settings, "GROQ_MAX_ACTIVE_PER_USER", 3)
    monkeypatch.setattr(settings, "GROQ_MAX_PROCESSING_PER_USER", 1)


def _set_capabilities(db, user_id, capabilities):
    row = db.query(BetaAccessGrant).filter_by(user_id=user_id).one()
    row.capabilities = sorted(capabilities)
    db.commit()


@pytest.fixture
def groq_context(db_context, auth_headers, monkeypatch):
    _configure(monkeypatch)
    from src.workers import meeting_intelligence_worker
    monkeypatch.setattr(meeting_intelligence_worker, "SessionLocal", db_context["session_factory"])
    db = db_context["session_factory"]()
    try:
        _set_capabilities(db, 1, CAPABILITIES)
    finally:
        db.close()
    meeting_id = seed_meeting(db_context["session_factory"])
    headers = auth_headers(scopes=["meeting_minutes", "read_transcriptions", "delete_transcriptions"])
    prefs = db_context["client"].patch("/settings/providers", headers=headers, json={
        "transcription_provider": "automatic", "intelligence_provider": "groq", "use_diarization": False,
    })
    assert prefs.status_code == 200, prefs.text
    return {**db_context, "meeting_id": meeting_id, "headers": headers}


def _request(context, suffix=""):
    return context["client"].post(f'/meetings/{context["meeting_id"]}/intelligence{suffix}', headers=context["headers"])


def _db(context):
    return context["session_factory"]()


def test_groq_explicit_selection_persists_provider_and_reservation(groq_context):
    response = _request(groq_context)
    assert response.status_code == 202, response.text
    db = _db(groq_context)
    try:
        row = db.get(MeetingIntelligence, response.json()["id"])
        call = db.query(IntelligencePlatformCall).filter_by(intelligence_id=row.id).one()
        budget = db.get(PlatformProviderBudget, "groq")
        assert (row.provider, row.credential_source, row.model) == ("groq", "platform", settings.GROQ_MODEL)
        assert call.state == "reserved" and call.reserved_cents > 0
        assert budget.reserved_cents == call.reserved_cents
        assert len(groq_context["queue"].enqueued) == 1
    finally:
        db.close()


@pytest.mark.parametrize("identity", ["guest", "free", "admin", "generic_beta"])
def test_groq_http_admission_requires_specific_capability(groq_context, auth_headers, identity):
    context = groq_context
    if identity in {"free", "generic_beta"}:
        db = _db(context)
        try:
            if identity == "free":
                db.query(BetaAccessGrant).filter_by(user_id=1).delete()
                db.commit()
            else:
                _set_capabilities(db, 1, CAPABILITIES - {"intelligence.groq.platform"})
        finally:
            db.close()
        headers = context["headers"]
    elif identity == "admin":
        db = _db(context)
        try:
            _set_capabilities(db, 1, CAPABILITIES - {"intelligence.groq.platform"})
        finally:
            db.close()
        headers = auth_headers(roles=["admin"], scopes=["meeting_minutes"])
    else:
        guest = context["client"].post("/guest/sessions")
        assert guest.status_code == 201
        headers = {"Authorization": f'Bearer {guest.json()["guest_token"]}'}
    response = context["client"].post(
        f'/meetings/{context["meeting_id"]}/intelligence', headers=headers)
    assert response.status_code == (401 if identity == "guest" else 403)
    db = _db(context)
    try:
        assert db.query(MeetingIntelligence).count() == 0
        assert db.query(IntelligencePlatformCall).count() == 0
    finally:
        db.close()


def test_groq_worker_real_usage_observer_and_grounded_persistence(groq_context, monkeypatch):
    context = groq_context
    requested = _request(context)
    intelligence_id = requested.json()["id"]
    received = {}

    class FakeGroqProvider:
        def __init__(self):
            self.observer = None

        def set_usage_observer(self, callback):
            self.observer = callback

        def generate(self, generation_context):
            received["context"] = copy.deepcopy(generation_context)
            self.observer({"status": "response", "prompt_tokens": 40, "completion_tokens": 20,
                           "total_tokens": 60, "cached_tokens": 5, "reasoning_tokens": 7})
            return json.dumps(valid_result())

    fake = FakeGroqProvider()
    calls = []
    def get_provider(*, provider=None, model=None, **kwargs):
        calls.append((provider, model, kwargs))
        return fake
    monkeypatch.setattr(worker, "get_provider", get_provider)
    assert worker.process_intelligence_job(intelligence_id)["status"] == "completed"
    assert calls == [("groq", settings.GROQ_MODEL, {})]
    assert received["context"]["segments"]
    db = _db(context)
    try:
        row = db.get(MeetingIntelligence, intelligence_id)
        call = db.query(IntelligencePlatformCall).filter_by(intelligence_id=intelligence_id).one()
        events = db.query(UsageEvent).filter_by(operation_id=row.usage_attempt_id).all()
        measured = {event.metric: event.quantity for event in events if event.measurement_source == "provider_response"}
        assert row.result == valid_result()
        assert call.state == "attempted"
        assert measured["input_tokens"] == Decimal(40)
        assert measured["output_tokens"] == Decimal(20)
        assert measured["total_tokens"] == Decimal(60)
        assert measured["cache_read_tokens"] == Decimal(5)
        assert measured["reasoning_tokens"] == Decimal(7)
        assert "reasoning_tokens" not in {event.metric for event in events if event.metric in {"output_tokens", "thinking_tokens"}}
        assert any(event.metric == "input_uncached_tokens" and event.quantity == Decimal(35) for event in events)
    finally:
        db.close()


def test_groq_revoke_after_enqueue_fails_before_provider_request(groq_context, monkeypatch):
    context = groq_context
    intelligence_id = _request(context).json()["id"]
    db = _db(context)
    try:
        _set_capabilities(db, 1, CAPABILITIES - {"intelligence.groq.platform"})
    finally:
        db.close()
    calls = []
    monkeypatch.setattr(worker, "get_provider", lambda **kwargs: calls.append(kwargs))
    with pytest.raises(RuntimeError, match="Meeting analysis failed"):
        worker.process_intelligence_job(intelligence_id)
    assert calls == []
    db = _db(context)
    try:
        row = db.get(MeetingIntelligence, intelligence_id)
        call = db.query(IntelligencePlatformCall).filter_by(intelligence_id=intelligence_id).one()
        assert row.status == "failed" and call.state == "reserved"
    finally:
        db.close()


def test_groq_never_falls_back_to_gemini_or_accepts_byok_route(groq_context, monkeypatch):
    context = groq_context
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "GEMINI_API_KEY_CONFIGURED", False)
    assert context["client"].post("/settings/providers/groq/credential", headers=context["headers"],
        json={"secret": "synthetic-user-key"}).status_code == 404
    db = _db(context)
    try:
        preference = db.get(UserProviderPreferences, 1)
        preference.intelligence_provider = "gemini"
        db.commit()
    finally:
        db.close()
    # Explicit Gemini is unavailable without its configured service; it does not silently switch to Groq.
    response = _request(context)
    assert response.status_code == 503
    db = _db(context)
    try:
        assert db.query(IntelligencePlatformCall).count() == 0
    finally:
        db.close()


def test_groq_missing_budget_refuses_before_paid_request(groq_context, monkeypatch):
    context = groq_context
    db = _db(context)
    try:
        db.add(PlatformProviderBudget(provider="groq", limit_cents=100, reserved_cents=100))
        db.commit()
    finally:
        db.close()
    # Admission should fail before a durable intelligence row or enqueue.
    response = _request(context)
    assert response.status_code == 429
    assert context["queue"].enqueued == []


def test_groq_active_and_processing_caps_are_enforced(groq_context, monkeypatch):
    context = groq_context
    ids = []
    for _ in range(3):
        meeting_id = seed_meeting(context["session_factory"])
        response = context["client"].post(f'/meetings/{meeting_id}/intelligence', headers=context["headers"])
        assert response.status_code == 202
        ids.append(response.json()["id"])
    meeting_id = seed_meeting(context["session_factory"])
    response = context["client"].post(f'/meetings/{meeting_id}/intelligence', headers=context["headers"])
    assert response.status_code == 429

    # The worker claim cap is exercised with two distinct users' rows sharing a fixture meeting owner.
    # Force a second pending Groq generation after the first is processing, preserving normal DB state checks.
    db = _db(context)
    try:
        rows = db.query(MeetingIntelligence).filter(MeetingIntelligence.id.in_(ids)).all()
        rows[0].status = "processing"
        rows[1].status = "pending"
        db.commit()
        second = rows[1].id
    finally:
        db.close()
    monkeypatch.setattr(worker, "get_provider", lambda **kwargs: pytest.fail("provider must not be called"))
    # A processing row at cap prevents claim; the attempted row becomes failed without making a request.
    with pytest.raises(RuntimeError, match="Meeting analysis failed"):
        worker.process_intelligence_job(second)
    db = _db(context)
    try:
        assert db.get(MeetingIntelligence, second).status == "failed"
    finally:
        db.close()


def test_groq_reservation_survives_deletion_and_attempt_is_never_repeated(groq_context, monkeypatch):
    context = groq_context
    intelligence_id = _request(context).json()["id"]
    db = _db(context)
    try:
        call = db.query(IntelligencePlatformCall).filter_by(intelligence_id=intelligence_id).one()
        held = call.reserved_cents
        call_id = call.id
    finally:
        db.close()
    class Failure:
        def set_usage_observer(self, _observer): pass
        def generate(self, _context):
            calls.append("generate")
            raise RuntimeError("synthetic provider failure")
    calls = []
    monkeypatch.setattr(worker, "get_provider", lambda **kwargs: Failure())
    with pytest.raises(RuntimeError):
        worker.process_intelligence_job(intelligence_id)
    assert worker.process_intelligence_job(intelligence_id)["status"] == "already_claimed_or_deleted"
    assert calls == ["generate"]
    db = _db(context)
    try:
        assert db.query(MeetingIntelligence).filter_by(id=intelligence_id).one().status == "failed"
    finally:
        db.close()
    # A fresh retry creates a new revision/hold. Deleting its resource preserves cumulative budget usage.
    retry = _request(context).json()
    assert retry["revision"] == 2
    assert context["client"].delete(f'/meetings/{context["meeting_id"]}', headers=context["headers"]).status_code == 200
    db = _db(context)
    try:
        old_call = db.get(IntelligencePlatformCall, call_id)
        budget = db.get(PlatformProviderBudget, "groq")
        assert old_call is not None and old_call.reserved_cents == held
        assert budget.reserved_cents >= held
        assert old_call.state == "attempted"
    finally:
        db.close()


def test_groq_ambiguous_recovery_fails_without_republishing_or_reexecuting(groq_context, monkeypatch):
    context = groq_context
    intelligence_id = _request(context).json()["id"]
    db = _db(context)
    try:
        row = db.get(MeetingIntelligence, intelligence_id)
        row.status = "processing"
        row.usage_attempt_id = "00000000-0000-4000-8000-000000000001"
        call = db.query(IntelligencePlatformCall).filter_by(intelligence_id=intelligence_id).one()
        call.state = "attempted"
        db.commit()
    finally:
        db.close()

    def missing_job(*_args, **_kwargs):
        raise NoSuchJobError
    monkeypatch.setattr(worker.Job, "fetch", missing_job)
    enqueued_before = len(context["queue"].enqueued)
    assert worker.recover_intelligence_jobs(context["queue"]) == 0
    assert len(context["queue"].enqueued) == enqueued_before
    provider_calls = []
    monkeypatch.setattr(worker, "get_provider", lambda **kwargs: provider_calls.append(kwargs))
    assert worker.process_intelligence_job(intelligence_id)["status"] == "already_claimed_or_deleted"
    assert provider_calls == []
    db = _db(context)
    try:
        assert db.get(MeetingIntelligence, intelligence_id).status == "failed"
        assert db.query(IntelligencePlatformCall).filter_by(intelligence_id=intelligence_id).one().state == "attempted"
    finally:
        db.close()
