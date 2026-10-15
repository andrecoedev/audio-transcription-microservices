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
    assert client.get("/admin/settings", headers=headers).json()["version"] == 2
    with db_context["session_factory"]() as db:
        event = db.query(AuditEvent).filter_by(event="admin.settings_changed").one()
        assert event.actor_user_id == 1
        assert event.event_metadata["before"]["beta.quota_minutes_per_participant"] == 600
        assert event.event_metadata["after"]["beta.quota_minutes_per_participant"] == 360
