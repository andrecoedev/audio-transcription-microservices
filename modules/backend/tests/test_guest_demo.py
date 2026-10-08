"""The public example is synthetic, read-only and cannot authorize inference."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.config import settings
from src.intelligence_schema import IntelligenceResult, validate_grounding
from src.models import Transcription, UsageEvent, PlatformProviderCall, PlatformProviderBudget
from src.routers import guests, transcriptions
from src.services import rate_limit
from src.services.platform_budget import begin_platform_call
from src.workers import transcription_worker


def test_demo_works_without_database_queue_or_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Demo touched private infrastructure")
    monkeypatch.setattr(transcriptions, "get_transcription_queue", forbidden)
    monkeypatch.setattr(rate_limit, "get_redis_connection", forbidden)
    app = FastAPI()
    app.include_router(guests.router)
    with TestClient(app) as client:
        data = client.get("/guest/demo").json()
        assert data["id"] == "usagi-demo-v1" and data["is_demo"] is True
        assert len(data["speakers"]) == 2
        content = IntelligenceResult.model_validate(data["intelligence"])
        validate_grounding(content, data["segments"], data["speakers"])
        assert content.action_items[1].assignee is None
        assert content.action_items[1].due_date is None
        ids = {item["id"] for item in data["speakers"]}
        for order, segment in enumerate(data["segments"]):
            assert segment["order"] == order and segment["speaker"] in ids
            assert 0 <= segment["start"] < segment["end"] <= data["duration_seconds"]
        # Each response is an independent copy, never a shared mutable template.
        data["segments"][0]["text"] = "changed"
        assert client.get("/guest/demo").json()["segments"][0]["text"] != "changed"


@pytest.mark.parametrize("model", ["assemblyai", "whisper", "gemini", "groq"])
def test_direct_guest_upload_is_denied_even_when_paid_flags_enabled(db_context, monkeypatch, model, wav_bytes):
    monkeypatch.setattr(settings, "AAI_GUEST_ENABLED", True)
    monkeypatch.setattr(settings, "AAI_PLATFORM_ENABLED", True)
    monkeypatch.setattr(settings, "AAI_API_KEY_CONFIGURED", True)
    monkeypatch.setattr(settings, "AAI_PLATFORM_BUDGET_CENTS", 200)
    monkeypatch.setattr(rate_limit, "get_redis_connection", lambda: pytest.fail("Denied upload touched Redis"))
    response = db_context["client"].post("/guest/transcriptions/jobs",
        files={"file": ("synthetic.wav", wav_bytes)}, data={"transcription_model": model})
    assert response.status_code == 403
    assert "demonstração" in response.json()["detail"]
    assert db_context["queue"].enqueued == []
    db = db_context["session_factory"]()
    assert db.query(Transcription).count() == db.query(UsageEvent).count() == 0
    assert db.query(PlatformProviderCall).count() == 0
    db.close()


@pytest.mark.parametrize("provider", ["whisper", "assemblyai"])
def test_recovered_guest_job_cannot_initialize_or_call_engines(db_context, monkeypatch, provider):
    from .test_public_guest import guest_headers, seed_legacy_guest_result
    guest = guest_headers(db_context["client"])
    _, tid = seed_legacy_guest_result(db_context, guest)
    db = db_context["session_factory"]()
    db.get(Transcription, tid).job.transcription_model = provider
    db.commit()
    monkeypatch.setattr(transcription_worker, "SessionLocal", db_context["session_factory"])
    monkeypatch.setattr(settings, "AAI_GUEST_ENABLED", True)
    for name in ("get_processing_service", "get_cloud_processing_service", "materialize_input", "begin_platform_call"):
        monkeypatch.setattr(transcription_worker, name, lambda *args: pytest.fail("Guest reached inference"))
    with pytest.raises(RuntimeError):
        transcription_worker.process_transcription_job_sync(tid)
    db.expire_all()
    row = db.get(Transcription, tid)
    assert row.status == row.job.status == "failed"
    # Re-delivery cannot turn a terminal denied job into a provider call.
    with pytest.raises(RuntimeError):
        transcription_worker.process_transcription_job_sync(tid)
    db.close()


def test_claimed_legacy_guest_reservation_cannot_start_paid_call(db_context, monkeypatch, auth_headers):
    from .test_public_guest import guest_headers, seed_legacy_guest_result
    guest = guest_headers(db_context["client"])
    _, tid = seed_legacy_guest_result(db_context, guest)
    db = db_context["session_factory"]()
    db.add(PlatformProviderBudget(provider="assemblyai", limit_cents=200, reserved_cents=1))
    db.flush()
    db.add(PlatformProviderCall(transcription_id=tid, provider="assemblyai", context="guest",
                               credential_source="platform", reserved_cents=1))
    db.commit()
    assert db_context["client"].post("/guest/claim", headers=auth_headers(),
        json={"guest_token": guest["Authorization"][7:]}).json()["transferred"] == 1
    monkeypatch.setattr(settings, "AAI_GUEST_ENABLED", True)
    monkeypatch.setattr(settings, "AAI_PLATFORM_ENABLED", True)
    with pytest.raises(RuntimeError, match="demonstration only"):
        begin_platform_call(db, tid)
    db.expire_all()
    assert db.query(PlatformProviderCall).one().state == "reserved"
    db.close()


@pytest.mark.parametrize("path,payload", [
    ("/transcriptions/jobs", {}),
    ("/meetings/1/intelligence", {}),
    ("/meetings/1/intelligence/regenerate", {}),
    ("/meeting-minutes/generate", {"transcription_id": 1, "title": "Exemplo"}),
])
def test_guest_proof_cannot_authorize_private_processing(db_context, path, payload):
    from .test_public_guest import guest_headers
    headers = guest_headers(db_context["client"])
    response = db_context["client"].post(path, headers=headers, json=payload)
    assert response.status_code == 401
    assert db_context["queue"].enqueued == []
