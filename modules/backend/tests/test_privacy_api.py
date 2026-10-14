"""Account data is returned only to its authenticated internal owner."""
from .test_privacy_lifecycle import _seed_owned_data
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from src.models import AuditEvent, Transcription, UserProviderPreferences, UsageEvent
import pytest

from .conftest import FakeRedisConnection


@pytest.mark.parametrize("path", ["/account/data", "/account/data?user_id=2"])
def test_export_requires_account(db_context, path):
    assert db_context["client"].get(path).status_code == 401


def test_export_rejects_other_account_selector(db_context, auth_headers):
    assert db_context["client"].get("/account/data?user_id=2", headers=auth_headers()).status_code == 422


def test_export_rate_limit_and_redis_unavailable(db_context, auth_headers, monkeypatch):
    from src.services import rate_limit
    from src.config import settings
    redis = FakeRedisConnection()
    monkeypatch.setattr(rate_limit, "get_redis_connection", lambda: redis)
    monkeypatch.setattr(settings, "PRIVACY_EXPORT_RATE_LIMIT_PER_USER", 1)
    client, headers = db_context["client"], auth_headers()
    assert client.get("/account/data", headers=headers).status_code == 200
    limited = client.get("/account/data", headers=headers)
    assert limited.status_code == 429
    assert "retry-after" in limited.headers
    def unavailable():
        raise ConnectionError("Synthetic Redis failure")
    monkeypatch.setattr(rate_limit, "get_redis_connection", unavailable)
    assert client.get("/account/data", headers=headers).status_code == 503


def test_export_endpoint_returns_only_current_account_data(db_context, auth_headers):
    own = _seed_owned_data(db_context["session_factory"], db_context["tmp_path"] / "own.wav")
    _seed_owned_data(db_context["session_factory"], db_context["tmp_path"] / "other.wav",
                     user_id=2, username="bob")
    response = db_context["client"].get("/account/data", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["user"]["id"] == 1
    assert [item["id"] for item in response.json()["transcriptions"]] == [own]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"] == 'attachment; filename="usagi-data.json"'


def test_export_excludes_diagnostics_and_internal_costs_but_includes_preferences_and_usage(
    db_context, auth_headers
):
    resource = _seed_owned_data(db_context["session_factory"], db_context["tmp_path"] / "own.wav")
    diagnostic_canary = secrets.token_urlsafe(24)
    db = db_context["session_factory"]()
    db.get(Transcription, resource).error_message = diagnostic_canary
    db.add(AuditEvent(actor_user_id=1, event="user.login", event_metadata={"debug": diagnostic_canary}))
    db.add(UserProviderPreferences(user_id=1, transcription_provider="automatic", intelligence_provider="automatic"))
    db.add(UsageEvent(id=str(uuid4()), operation_id="synthetic-usage", user_id=1,
        resource_type="transcription", resource_id=str(resource), operation="transcription",
        provider="whisper", credential_source="local", metric="audio_seconds", unit="second",
        quantity=Decimal("120"), status="completed", occurred_at=datetime.now(timezone.utc),
        measurement_source="ffmpeg", currency="USD", estimated_cost=Decimal("0.123"), cost_scope="usagi"))
    db.commit()
    db.close()
    response = db_context["client"].get("/account/data", headers=auth_headers())
    assert response.status_code == 200
    assert diagnostic_canary not in response.text
    assert "opaque.wav" not in response.text
    assert "estimated_cost" not in response.text
    assert response.json()["preferences"]["transcription_provider"] == "automatic"
    assert response.json()["usage"][0]["metric"] == "audio_seconds"
    assert Decimal(response.json()["usage"][0]["quantity"]) == Decimal("120")
