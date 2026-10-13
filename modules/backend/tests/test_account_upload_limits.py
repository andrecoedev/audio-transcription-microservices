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
        with db_context["session_factory"]() as db:
            assert db.get(User, user_id).plan == "free"
    assert client.get("/guest/policy").json()["max_upload_mb"] == settings.PUBLIC_MAX_UPLOAD_MB
    assert client.get("/settings/providers").status_code == 401


def test_streaming_size_and_multipart_limits(db_context, monkeypatch, wav_bytes):
    monkeypatch.setattr(settings, "PUBLIC_MAX_UPLOAD_MB", 1)
    monkeypatch.setattr(settings, "LARGE_UPLOAD_USER_IDS", [1])
    monkeypatch.setattr(settings, "LARGE_UPLOAD_SIZE_MB", 2)
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
