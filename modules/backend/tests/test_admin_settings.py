"""Administrative policy HTTP contract; no provider requests or real secrets."""
from src.models import User


def admin_headers(context, factory):
    with context["session_factory"]() as db:
        db.get(User, 1).is_superuser = True
        db.commit()
    return factory()


def test_settings_requires_admin_and_never_bootstraps_on_read(db_context, auth_headers):
    client = db_context["client"]
    assert client.get("/admin/settings").status_code == 401
    assert client.get("/admin/settings", headers=auth_headers()).status_code == 403
    with db_context["session_factory"]() as db:
        db.get(User, 1).is_superuser = True
        db.commit()
    response = client.get("/admin/settings", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["version"] == 0
    assert response.json()["values"]["beta.enabled"] is False


def test_initialization_is_explicit_and_never_imports_enabled_flags(db_context, auth_headers, monkeypatch):
    from src.config import settings
    monkeypatch.setattr(settings, "AAI_PLATFORM_ENABLED", True)
    headers = admin_headers(db_context, auth_headers)
    response = db_context["client"].post("/admin/settings/initialize", headers=headers,
        json={"version": 0, "confirmed": True})
    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["version"] == 1
    assert response.json()["values"]["beta.enabled"] is False
    assert response.json()["values"]["assemblyai.platform_enabled"] is False
    assert response.json()["values"]["assemblyai.hard_stop_usd"] == "0"


def test_updates_are_allowlisted_confirmed_versioned_and_audited(db_context, auth_headers):
    from src.models import AuditEvent
    client = db_context["client"]
    headers = admin_headers(db_context, auth_headers)
    client.post("/admin/settings/initialize", headers=headers, json={"version": 0, "confirmed": True}).raise_for_status()
    assert client.patch("/admin/settings/beta", headers=headers,
        json={"version": 1, "quota_minutes_per_participant": 360}).status_code == 422
    assert client.patch("/admin/settings/assemblyai", headers=headers,
        json={"version": 1, "model": "other"}).status_code == 422
    assert client.patch("/admin/settings/beta", headers=headers,
        json={"version": 1, "enabled": "true"}).status_code == 422
    response = client.patch("/admin/settings/beta", headers=headers,
        json={"version": 1, "confirmed": True, "quota_minutes_per_participant": 360})
    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["values"]["beta.quota_minutes_per_participant"] == 360
    stale = client.patch("/admin/settings/beta", headers=headers,
        json={"version": 1, "round_name": "Outdated"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "admin_settings_revision_conflict"
    assert client.get("/admin/settings", headers=headers).json()["version"] == 2
    with db_context["session_factory"]() as db:
        event = db.query(AuditEvent).filter_by(event="admin.settings_changed").one()
        assert event.actor_user_id == 1
        assert event.event_metadata["before"]["beta.quota_minutes_per_participant"] == 600
        assert event.event_metadata["after"]["beta.quota_minutes_per_participant"] == 360


def test_reduced_budget_preserves_committed_use_and_blocks_new_calls(db_context, auth_headers, monkeypatch):
    from decimal import Decimal
    import pytest
    from fastapi import HTTPException
    from src.models import PlatformProviderBudget, Transcription
    from src.services.platform_budget import reserve_platform_call
    from .platform_helpers import configure_platform, confirm_test_balance
    configure_platform(monkeypatch)
    headers = admin_headers(db_context, auth_headers)
    client = db_context["client"]
    client.post("/admin/settings/initialize", headers=headers, json={"version": 0, "confirmed": True}).raise_for_status()
    with db_context["session_factory"]() as db:
        confirm_test_balance(db)
        budget = db.get(PlatformProviderBudget, "assemblyai")
        budget.limit_cents = Decimal(1500)
        budget.reserved_cents = Decimal(800)
        budget.operational_policy = {**budget.operational_policy, "beta_enabled": True, "platform_enabled": True}
        db.commit()
    response = client.patch("/admin/settings/assemblyai", headers=headers,
        json={"version": 1, "confirmed": True, "hard_stop_usd": "6", "alert_usd": "5"})
    assert response.status_code == 200
    with db_context["session_factory"]() as db:
        assert db.get(PlatformProviderBudget, "assemblyai").reserved_cents == Decimal(800)
        row = Transcription(filename="synthetic.wav", original_filename="synthetic.wav", file_size_mb=0.1, duration_seconds=60, transcription_model="assemblyai", status="queued")
        db.add(row)
        db.flush()
        with pytest.raises(HTTPException) as denied:
            reserve_platform_call(db, row.id, "local", duration_seconds=60)
        assert denied.value.status_code == 429


def test_paused_beta_blocks_admission_even_with_stale_enabled_environment(db_context, auth_headers, monkeypatch):
    import pytest
    from fastapi import HTTPException
    from src.models import Transcription
    from src.services.platform_budget import reserve_platform_call
    from .platform_helpers import configure_platform, confirm_test_balance
    configure_platform(monkeypatch)
    headers = admin_headers(db_context, auth_headers)
    db_context["client"].post("/admin/settings/initialize", headers=headers,
        json={"version": 0, "confirmed": True}).raise_for_status()
    with db_context["session_factory"]() as db:
        confirm_test_balance(db)
        row = Transcription(filename="synthetic.wav", original_filename="synthetic.wav", file_size_mb=0.1, duration_seconds=60, transcription_model="assemblyai", status="queued")
        db.add(row)
        db.flush()
        with pytest.raises(HTTPException) as denied:
            reserve_platform_call(db, row.id, "local", duration_seconds=60)
        assert denied.value.status_code == 503


def test_operational_views_are_admin_only_and_exclude_external_balance_and_secrets(db_context, auth_headers, monkeypatch):
    from src.routers import health
    monkeypatch.setattr(health, "_processing_status", lambda: {"redis": "connected", "worker_available": False,
        "worker_count": 0, "queue": "transcriptions"})
    headers = admin_headers(db_context, auth_headers)
    client = db_context["client"]
    client.post("/admin/settings/initialize", headers=headers, json={"version": 0, "confirmed": True}).raise_for_status()
    for path in ("overview", "participants", "history", "accounts?q=alice"):
        assert client.get(f"/admin/settings/{path}", headers=auth_headers("bob")).status_code == 403
        response = client.get(f"/admin/settings/{path}", headers=headers)
        assert response.status_code == 200
        assert not any(key in response.text for key in ("external_balance_snapshot_usd", "key_reference", "project_reference", "ciphertext", "hashed_password"))
    overview = client.get("/admin/settings/overview", headers=headers).json()
    assert overview["financial"]["available_usd"] == "0"
    assert overview["financial"]["authorized_usd"] == "0"
    assert overview["system"]["worker_available"] is False
    accounts = client.get("/admin/settings/accounts?q=alice", headers=headers).json()
    assert [a["user_id"] for a in accounts["items"]] == [1]
    assert client.get("/admin/settings/accounts?q=%25%25", headers=headers).json()["items"] == []
    history = client.get("/admin/settings/history", headers=headers).json()
    assert history["items"][0]["event"] == "admin.settings_initialized"


def test_quota_reduction_below_eight_committed_hours_keeps_history(db_context, auth_headers):
    from datetime import datetime, timezone
    from decimal import Decimal
    from src.models import TranscriptionReservation
    headers = admin_headers(db_context, auth_headers)
    client = db_context["client"]
    client.post("/admin/settings/initialize", headers=headers, json={"version": 0, "confirmed": True}).raise_for_status()
    with db_context["session_factory"]() as db:
        for identity, state, seconds in [("finished", "consumed", 21600), ("pending", "unknown", 7200)]:
            db.add(TranscriptionReservation(id=identity, operation_key="synthetic:" + identity,
                user_id=1, period_start=datetime.now(timezone.utc).date(), round_id="test-round",
                source="usagi", provider="assemblyai", credential_source="platform", state=state,
                reserved_seconds=seconds, stored_bytes=0, input_reference="synthetic:" + identity))
        db.commit()
    response = client.patch("/admin/settings/beta", headers=headers,
        json={"version": 1, "confirmed": True, "quota_minutes_per_participant": 360})
    assert response.status_code == 200
    own = client.get("/account/plan", headers=headers).json()["quota"]
    assert Decimal(own["consumed_seconds"]) == 21600
    assert Decimal(own["reserved_seconds"]) == 7200
    assert Decimal(own["available_seconds"]) == 0
    participant = client.get("/admin/settings/participants", headers=headers).json()["items"][0]
    assert participant["committed_above_limit"] is True
    with db_context["session_factory"]() as db:
        assert db.get(TranscriptionReservation, "pending").state == "unknown"
        assert db.query(TranscriptionReservation).count() == 2


def test_limits_show_environment_ceiling_but_preserve_individual_upload_exception(db_context, auth_headers, monkeypatch):
    from src.config import settings
    from src.services.upload_policy import upload_limit_mb
    headers = admin_headers(db_context, auth_headers)
    client = db_context["client"]
    client.post("/admin/settings/initialize", headers=headers, json={"version": 0, "confirmed": True}).raise_for_status()
    monkeypatch.setattr(settings, "AAI_MAX_AUDIO_SECONDS", 120)
    view = client.get("/admin/settings", headers=headers).json()
    assert view["values"]["limits.max_audio_seconds"] == 120
    assert view["saved_values"]["limits.max_audio_seconds"] == 600
    assert "limits.max_audio_seconds" in view["overrides"]
    # Environment changes must not prevent an emergency pause or a label edit.
    assert client.patch("/admin/settings/beta", headers=headers,
        json={"version": 1, "round_name": "Rodada teste"}).status_code == 200
    assert client.patch("/admin/settings/limits", headers=headers,
        json={"version": 2, "max_upload_mb": 5}).status_code == 200
    monkeypatch.setattr(settings, "LARGE_UPLOAD_USER_IDS", [1])
    with db_context["session_factory"]() as db:
        assert upload_limit_mb(2, "public", db=db) == 5
        assert upload_limit_mb(1, "public", db=db) == min(settings.LARGE_UPLOAD_SIZE_MB, settings.MAX_UPLOAD_SIZE_MB)


def test_worker_uses_db_price_and_policy_and_finishes_submitted_call_after_pause(db_context, monkeypatch):
    from decimal import Decimal
    from src.config import settings
    from src.models import PlatformProviderBudget, PlatformProviderCall, Transcription
    from src.services import platform_budget as finance
    from src.services.beta_settings import update_policy
    from .platform_helpers import configure_platform, confirm_test_balance
    configure_platform(monkeypatch)
    with db_context["session_factory"]() as db:
        confirm_test_balance(db)
        row = Transcription(filename="synthetic.wav", original_filename="synthetic.wav", file_size_mb=0.1,
            duration_seconds=60, transcription_model="assemblyai", status="queued")
        db.add(row)
        db.flush()
        finance.reserve_platform_call(db, row.id, "local", duration_seconds=60)
        db.commit()
        # Simulate an API/Worker process whose old deployment values differ.
        monkeypatch.setattr(settings, "AAI_PLATFORM_ENABLED", False)
        monkeypatch.setattr(settings, "AAI_PLATFORM_BUDGET_CENTS", 0)
        monkeypatch.setattr(settings, "AAI_BETA_ROUND_ID", "outdated-round")
        monkeypatch.setattr(settings, "AAI_PLATFORM_HOURLY_USD", Decimal(0))
        monkeypatch.setattr(settings, "AAI_PLATFORM_PRICE_VERSION", "outdated-price")
        assert finance.begin_platform_call(db, row.id, duration_seconds=60) == "local"
        budget = db.get(PlatformProviderBudget, "assemblyai")
        update_policy(db, section="beta", changes={"beta.enabled": False},
            version=budget.configuration_version, confirmed=True, actor_user_id=1)
        db.commit()
        finance.observe_platform_call(db, row.id, {"provider_id": "synthetic-final", "status": "completed",
            "audio_duration_seconds": 60})
        db.commit()
        call = db.query(PlatformProviderCall).one()
        assert call.provider_status == "completed" and call.released_at is None
        assert call.price_version == "synthetic-price-version"
        assert call.estimated_cost_cents == Decimal("0.38333334")


def test_missing_or_invalid_policy_fails_closed_without_implicit_bootstrap(db_context, monkeypatch):
    import pytest
    from fastapi import HTTPException
    from src.models import PlatformProviderBudget
    from src.services import platform_budget as finance
    from .platform_helpers import configure_platform
    configure_platform(monkeypatch)
    with db_context["session_factory"]() as db:
        assert finance.platform_budget_has_headroom(db) is False
        assert db.query(PlatformProviderBudget).count() == 0
        db.add(PlatformProviderBudget(provider="assemblyai", limit_cents=1500, reserved_cents=0,
            operational_policy={"beta_enabled": "true", "unknown": True}))
        db.commit()
        assert finance.platform_budget_has_headroom(db) is False
        with pytest.raises(HTTPException) as denied:
            finance.reserve_platform_call(db, 999, "local", duration_seconds=60)
        assert denied.value.status_code == 503
