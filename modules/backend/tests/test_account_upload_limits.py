"""Upload exceptions cannot grant plans, processing access or admin bypasses."""

import pytest
from pydantic import ValidationError

from src.config import Settings, settings
from src.models import User
from src.security import create_access_token
from src.services.upload_policy import upload_limit_mb


def public_headers(user_id):
    token = create_access_token({"sub": str(user_id), "registration_source": "public",
                                 "scopes": ["transcribe", "read_transcriptions"]})
    return {"Authorization": "Bearer " + token}


def test_exception_is_opt_in_and_capped(monkeypatch):
    monkeypatch.setattr(settings, "LARGE_UPLOAD_USER_IDS", [1])
    monkeypatch.setattr(settings, "LARGE_UPLOAD_SIZE_MB", 5120)
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 5120)
    assert upload_limit_mb(1) == 5120
    assert upload_limit_mb(2) == settings.PUBLIC_MAX_UPLOAD_MB
    assert upload_limit_mb(None) == settings.PUBLIC_MAX_UPLOAD_MB
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1024)
    assert upload_limit_mb(1) == 1024
    monkeypatch.setattr(settings, "LARGE_UPLOAD_USER_IDS", [])
    assert upload_limit_mb(1) == settings.PUBLIC_MAX_UPLOAD_MB


@pytest.mark.parametrize("kwargs", [
    {"LARGE_UPLOAD_USER_IDS": [0]}, {"LARGE_UPLOAD_USER_IDS": [-1]},
    {"LARGE_UPLOAD_SIZE_MB": 0}, {"LARGE_UPLOAD_SIZE_MB": 5121},
])
def test_invalid_exception_configuration_fails(kwargs):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **kwargs)


@pytest.mark.parametrize("field", ["DEV_LOCAL_MAX_AUDIO_SECONDS",
    "DEV_LOCAL_MAX_QUEUED_JOBS", "DEV_LOCAL_MAX_PROCESSING_JOBS"])
def test_development_technical_caps_must_be_positive(field):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: 0})


def test_authenticated_policy_is_account_scoped(db_context, monkeypatch):
    monkeypatch.setattr(settings, "LARGE_UPLOAD_USER_IDS", [1])
    with db_context["session_factory"]() as db:
        for user_id in (1, 2):
            row = db.get(User, user_id)
            row.registration_source = "public"
            row.is_superuser = True
        db.commit()
    client = db_context["client"]
    for user_id, expected in [(1, 5120), (2, settings.PUBLIC_MAX_UPLOAD_MB)]:
        response = client.get("/settings/providers", headers=public_headers(user_id))
        assert response.status_code == 200
        assert response.json()["upload_policy"]["max_upload_mb"] == expected
        assert response.json()["upload_policy"]["max_audio_seconds"] == settings.PUBLIC_MAX_AUDIO_SECONDS
        with db_context["session_factory"]() as db:
            assert db.get(User, user_id).plan == "free"
    assert client.get("/guest/policy").json()["max_upload_mb"] == settings.PUBLIC_MAX_UPLOAD_MB
    assert client.get("/settings/providers").status_code == 401


def test_development_upload_policy_is_explicit_and_technically_capped(db_context, monkeypatch):
    from src.models import AuditEvent, BetaAccessGrant
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    monkeypatch.setattr(settings, "DEV_LOCAL_ACCESS_ENABLED", True)
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_ENABLED", True)
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 2)
    with db_context["session_factory"]() as db:
        # This regression exercises local-only development, not the separate
        # finite platform round granted by the shared positive test fixture.
        for grant in db.query(BetaAccessGrant).filter_by(user_id=1):
            grant.capabilities = [cap for cap in grant.capabilities if cap != "transcription.platform"]
        user = db.get(User, 1)
        user.registration_source = "public"
        user.is_superuser = True
        db.commit()
    client = db_context["client"]
    granted = client.patch("/admin/accounts/1/development-local-access",
        headers=public_headers(1), json={"enabled": True, "reason": "operational_access"})
    assert granted.status_code == 200, granted.text
    policy = client.get("/settings/providers", headers=public_headers(1)).json()["upload_policy"]
    assert policy["development_access"] is True
    assert policy["max_upload_mb"] == 2
    assert policy["max_audio_seconds"] == settings.DEV_LOCAL_MAX_AUDIO_SECONDS
    plan = client.get("/account/plan", headers=public_headers(1))
    assert plan.status_code == 200, plan.text
    assert plan.json()["development_access"] is True
    assert plan.json()["quota"]["limit_seconds"] is None
    assert plan.json()["quota"]["available_seconds"] is None
    revoked = client.patch("/admin/accounts/1/development-local-access",
        headers=public_headers(1), json={"enabled": False, "reason": "operational_access"})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["development_local_access"] is False
    with db_context["session_factory"]() as db:
        events = db.query(AuditEvent).filter_by(
            event="account.development_local_access_changed").order_by(AuditEvent.id).all()
        assert [event.event_metadata for event in events] == [
            {"previous": False, "new": True, "reason": "operational_access"},
            {"previous": True, "new": False, "reason": "operational_access"},
        ]


def test_development_access_grant_requires_admin_and_dev_flag(db_context, monkeypatch):
    from src.config import settings
    client = db_context["client"]
    ordinary = client.patch("/admin/accounts/2/development-local-access",
        headers=public_headers(1), json={"enabled": True, "reason": "operational_access"})
    assert ordinary.status_code == 403
    monkeypatch.setattr(settings, "APP_ENV", "prod")
    monkeypatch.setattr(settings, "DEV_LOCAL_ACCESS_ENABLED", True)
    with db_context["session_factory"]() as db:
        db.get(User, 1).is_superuser = True
        db.commit()
    denied = client.patch("/admin/accounts/2/development-local-access",
        headers=public_headers(1), json={"enabled": True, "reason": "operational_access"})
    assert denied.status_code == 403
    with db_context["session_factory"]() as db:
        assert not db.get(User, 2).development_local_access


def test_development_access_token_field_comes_from_persisted_user(db_context, monkeypatch):
    from src.config import settings
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    monkeypatch.setattr(settings, "DEV_LOCAL_ACCESS_ENABLED", True)
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_ENABLED", True)
    with db_context["session_factory"]() as db:
        db.get(User, 1).development_local_access = True
        db.commit()
    forged = create_access_token({"sub": "2", "development_local_access": True})
    response = db_context["client"].get("/settings/providers",
        headers={"Authorization": "Bearer " + forged})
    assert response.status_code == 200
    assert response.json()["upload_policy"]["development_access"] is False


def test_development_grant_body_is_bounded_before_parsing(db_context):
    response = db_context["client"].patch("/admin/accounts/1/development-local-access",
        headers=public_headers(1),
        json={"enabled": True, "reason": "x" * (32 * 1024)})
    assert response.status_code == 413


def test_streaming_size_and_multipart_limits(db_context, monkeypatch, wav_bytes):
    from src.utils import http_limits
    monkeypatch.setattr(settings, "PUBLIC_MAX_UPLOAD_MB", 1)
    monkeypatch.setattr(settings, "LARGE_UPLOAD_USER_IDS", [1])
    monkeypatch.setattr(settings, "LARGE_UPLOAD_SIZE_MB", 2)
    monkeypatch.setattr(http_limits, "SessionLocal", db_context["session_factory"])
    with db_context["session_factory"]() as db:
        for user_id in (1, 2):
            db.get(User, user_id).registration_source = "public"
        db.commit()
    client = db_context["client"]
    audio = wav_bytes + b"\0" * (1024 * 1024)
    selected = client.post("/transcriptions/jobs", headers=public_headers(1),
                           files={"file": ("sample.wav", audio)})
    assert selected.status_code == 202, selected.text
    other = client.post("/transcriptions/jobs", headers=public_headers(2),
                        files={"file": ("sample.wav", audio)})
    assert other.status_code == 413
    above_cap = client.post("/transcriptions/jobs", headers=public_headers(1),
                            files={"file": ("sample.wav", audio * 2)})
    assert above_cap.status_code == 413
    assert len(db_context["queue"].enqueued) == 1


def test_dev_account_upload_uses_db_flag_and_technical_limits(db_context, monkeypatch, wav_bytes):
    from types import SimpleNamespace
    from sqlalchemy.orm import Session
    from src.models import TranscriptionJob
    from src.utils import http_limits
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    monkeypatch.setattr(settings, "DEV_LOCAL_ACCESS_ENABLED", True)
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_ENABLED", True)
    monkeypatch.setattr(settings, "PUBLIC_MAX_UPLOAD_MB", 1)
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 2)
    monkeypatch.setattr(http_limits, "SessionLocal", db_context["session_factory"])
    real_get_bind = Session.get_bind
    def test_get_bind(self, mapper=None, clause=None, **kwargs):
        if mapper is None and clause is None and not kwargs:
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        return real_get_bind(self, mapper=mapper, clause=clause, **kwargs)
    monkeypatch.setattr(Session, "get_bind", test_get_bind)
    with db_context["session_factory"]() as db:
        user = db.get(User, 1)
        user.registration_source = "public"
        user.development_local_access = True
        db.commit()
    audio = wav_bytes + b"\0" * (1024 * 1024)
    response = db_context["client"].post("/transcriptions/jobs", headers=public_headers(1),
                                         files={"file": ("sample.wav", audio)})
    assert response.status_code == 202, response.text
    with db_context["session_factory"]() as db:
        job_row = db.query(TranscriptionJob).one()
        assert job_row.max_duration_seconds == settings.DEV_LOCAL_MAX_AUDIO_SECONDS
        assert job_row.timeout_seconds is None
