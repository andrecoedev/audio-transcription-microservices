from datetime import datetime, timedelta, timezone

import pytest

from src.config import settings
from src.models import GuestSession, Transcription, TranscriptionOwnership, User
from src.security import create_access_token
from src.services.guest_retention import apply_guest_retention
from src.services import rate_limit
from .conftest import FakeRedisConnection


@pytest.fixture(autouse=True)
def simulated_guest_provider_admission(monkeypatch):
    # These ownership/upload regressions use a fake queue, never paid calls.
    # P4-04 admission is simulated only here; production remains fail-closed.
    from src.routers import transcriptions
    monkeypatch.setattr(transcriptions, "require_guest_processing", lambda: None)
    monkeypatch.setattr(transcriptions, "reserve_platform_call", lambda *_args: None)


def test_guest_processing_blocked_by_provider_recovery_without_local_fallback(db_context, monkeypatch, wav_bytes):
    from src.routers import transcriptions
    from src.services.provider_policy import require_guest_processing
    monkeypatch.setattr(transcriptions, "require_guest_processing", require_guest_processing)
    client = db_context["client"]
    policy = client.get("/guest/policy").json()
    assert policy["provider"] == "assemblyai" and policy["diarization"] is True
    assert policy["can_create_job"] is False and policy["blocked_by"] == "P4-04"
    assert policy["max_upload_mb"] == settings.PUBLIC_MAX_UPLOAD_MB
    assert policy["max_audio_seconds"] == settings.PUBLIC_MAX_AUDIO_SECONDS
    assert policy["allowed_extensions"] == settings.allowed_extensions_list
    guest = guest_headers(client)
    response = client.post("/guest/transcriptions/jobs", headers=guest,
        files={"file": ("synthetic.wav", wav_bytes)}, data={"use_diarization": "true"})
    assert response.status_code == 503
    assert db_context["queue"].enqueued == []
    assert client.get("/guest/session", headers=guest).json()["jobs_created"] == 0


def test_simulated_guest_assemblyai_admission_preserves_speaker_option(db_context, wav_bytes):
    client = db_context["client"]
    response = client.post("/guest/transcriptions/jobs", headers=guest_headers(client),
        files={"file": ("synthetic.wav", wav_bytes)}, data={"use_diarization": "true"})
    assert response.status_code == 202
    db = db_context["session_factory"]()
    job = db.get(Transcription, response.json()["id"]).job
    assert job.transcription_model == "assemblyai" and job.use_diarization is True
    db.close()


def guest_headers(client):
    response = client.post("/guest/sessions")
    assert response.status_code == 201
    return {"Authorization": "Bearer " + response.json()["guest_token"]}


def signup(client, username="visitor"):
    return client.post("/auth/signup", json={"username": username,
        "email": username + "@example.test", "password": "a safe test password"})


def test_signup_login_persistent_non_admin_identity(db_context):
    client = db_context["client"]
    response = signup(client)
    assert response.status_code == 201
    user = response.json()["user"]
    assert user["registration_source"] == "public"
    assert user["roles"] == ["user"]
    assert "manage_keys" not in user["scopes"]
    login = client.post("/auth/login", json={"username": "visitor", "password": "a safe test password"})
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert client.get("/auth/me", headers=headers).json()["user"]["registration_source"] == "public"
    assert client.get("/api-keys", headers=headers).status_code in {403, 404}
    assert signup(client).status_code == 400


@pytest.mark.parametrize("username,email,password", [
    ("admin", "valid@example.test", "valid password here"),
    ("ADMIN", "valid@example.test", "valid password here"),
    ("valid", "invalid", "valid password here"),
    ("valid", "valid@example.test", "short"),
    ("valid", "valid@example.test", "é" * 40),
    ("guest:fake", "valid@example.test", "valid password here"),
])
def test_signup_rejects_reserved_or_invalid_identity(db_context, username, email, password):
    response = db_context["client"].post("/auth/signup", json={"username": username,
        "email": email, "password": password, "is_superuser": True, "registration_source": "local"})
    assert response.status_code == 400
    assert password not in response.text


def test_signup_cannot_claim_unresolved_legacy_username(db_context):
    db = db_context["session_factory"]()
    row = Transcription(filename="legacy.wav", original_filename="legacy.wav", file_size_mb=1,
                        duration_seconds=1, transcription_model="whisper", segments=[], status="completed")
    db.add(row)
    db.flush()
    db.add(TranscriptionOwnership(transcription_id=row.id, owner_sub="visitor"))
    db.commit()
    assert signup(db_context["client"]).status_code == 400
    assert db.query(User).filter_by(username="visitor").count() == 0
    assert db.query(TranscriptionOwnership).one().user_id is None
    db.close()


def test_public_registration_fields_cannot_grant_platform_credentials(db_context, wav_bytes, monkeypatch):
    client = db_context["client"]
    registered = client.post("/auth/signup", json={"username": "visitor", "email": "visitor@example.test",
        "password": "safe test password", "roles": ["admin"], "registration_source": "local"})
    headers = {"Authorization": "Bearer " + registered.json()["access_token"]}
    assert client.post("/transcriptions/jobs", headers=headers,
        files={"file": ("audio.wav", wav_bytes)}, data={"transcription_model": "assemblyai"}).status_code == 403
    local = client.post("/transcriptions/jobs", headers=headers, files={"file": ("audio.wav", wav_bytes)})
    assert local.status_code == 202
    db = db_context["session_factory"]()
    row = db.get(Transcription, local.json()["id"])
    row.status = row.job.status = "completed"
    row.segments = [{"start": 0, "end": 1, "speaker": "SPEAKER_00", "text": "teste"}]
    from src.models import Meeting
    db.add(Meeting(id=row.id, title="test"))
    db.commit()
    monkeypatch.setattr(settings, "GEMINI_API_KEY_CONFIGURED", True)
    assert client.post(f"/meetings/{row.id}/intelligence", headers=headers).status_code == 403
    assert client.post("/meeting-minutes/generate", headers=headers,
        json={"transcription_id": row.id, "title": "test"}).status_code == 403
    assert row.job.max_duration_seconds == settings.PUBLIC_MAX_AUDIO_SECONDS
    assert db_context["queue"].enqueued[0][2]["job_timeout"] == settings.PUBLIC_JOB_TIMEOUT_SECONDS
    db.close()


def test_signed_claims_do_not_override_public_account_origin(db_context, wav_bytes):
    client = db_context["client"]
    registered = signup(client).json()
    token = create_access_token({"sub": str(registered["user"]["id"]), "registration_source": "local",
                                 "roles": ["admin"], "scopes": ["transcribe"]})
    headers = {"Authorization": "Bearer " + token}
    assert client.get("/auth/me", headers=headers).json()["user"]["roles"] == ["user"]
    assert client.post("/transcriptions/jobs", headers=headers,
        data={"transcription_model": "assemblyai"}, files={"file": ("test.wav", wav_bytes)}).status_code == 403


def test_guest_isolation_private_routes_and_safe_conversion(db_context, auth_headers, wav_bytes):
    client = db_context["client"]
    guest = guest_headers(client)
    other = guest_headers(client)
    filename = "Reunião de equipe.wav"
    job = client.post("/guest/transcriptions/jobs", headers=guest, files={"file": (filename, wav_bytes)})
    assert job.status_code == 202
    tid = job.json()["id"]
    guest_result = client.get(f"/guest/transcriptions/{tid}", headers=guest)
    assert guest_result.status_code == 200
    assert guest_result.json()["original_filename"] == filename
    assert client.get(f"/guest/transcriptions/{tid}", headers=other).status_code == 404
    assert client.get(f"/transcriptions/{tid}", headers=guest).status_code == 401
    assert client.get(f"/transcriptions/{tid}", headers=auth_headers()).status_code == 404
    assert client.get("/guest/session", headers=auth_headers()).status_code == 401
    assert client.delete(f"/guest/transcriptions/{tid}", headers=guest).status_code == 409
    assert client.post("/guest/claim", json={"guest_token": guest["Authorization"][7:]}).status_code == 401
    assert client.post("/guest/claim", headers=auth_headers(), json={"guest_token": other["Authorization"][7:], "id": tid}).json()["transferred"] == 0
    claimed = client.post("/guest/claim", headers=auth_headers(), json={"guest_token": guest["Authorization"][7:]})
    assert claimed.json()["transferred"] == 1
    assert client.get(f"/transcriptions/{tid}", headers=auth_headers()).status_code == 200
    assert client.get(f"/transcriptions/{tid}", headers=auth_headers("bob")).status_code == 404
    assert client.get(f"/guest/transcriptions/{tid}", headers=guest).status_code == 401
    assert client.post("/guest/claim", headers=auth_headers(), json={"guest_token": guest["Authorization"][7:]}).json()["transferred"] == 0
    assert client.post("/guest/claim", headers=auth_headers("bob"), json={"guest_token": guest["Authorization"][7:]}).status_code == 403


def test_guest_expiry_and_job_budget_are_server_side(db_context, wav_bytes):
    client = db_context["client"]
    headers = guest_headers(client)
    for expected in (202, 429):
        assert client.post("/guest/transcriptions/jobs", headers=headers,
                           files={"file": ("test.wav", wav_bytes)}).status_code == expected
    db = db_context["session_factory"]()
    db.query(GuestSession).one().expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert client.get("/guest/session", headers=headers).status_code == 401
    assert client.post("/guest/claim", headers=headers, json={"guest_token": headers["Authorization"][7:]}).status_code == 401
    db.close()


@pytest.mark.parametrize("options", [{"transcription_model": "whisper"}])
def test_guest_cannot_enable_expensive_providers(db_context, wav_bytes, options):
    client = db_context["client"]
    headers = guest_headers(client)
    assert client.post("/guest/transcriptions/jobs", headers=headers, data=options,
        files={"file": ("test.wav", wav_bytes)}).status_code == 403
    assert client.get("/guest/session", headers=headers).json()["jobs_created"] == 0
    assert db_context["queue"].enqueued == []


def test_public_budgets_and_redis_failure_are_fail_closed(db_context, monkeypatch):
    client = db_context["client"]
    redis = FakeRedisConnection()
    monkeypatch.setattr(rate_limit, "get_redis_connection", lambda: redis)
    monkeypatch.setattr(settings, "GUEST_SESSION_RATE_LIMIT_PER_IP", 1)
    assert client.post("/guest/sessions").status_code == 201
    limited = client.post("/guest/sessions")
    assert limited.status_code == 429 and "Retry-After" in limited.headers
    def unavailable():
        raise RuntimeError("unavailable")
    monkeypatch.setattr(rate_limit, "get_redis_connection", unavailable)
    assert client.post("/guest/sessions").status_code == 503
    assert signup(client).status_code == 503


def test_guest_retention_dry_run_repeated_and_active_preservation(db_context, wav_bytes):
    client = db_context["client"]
    headers = guest_headers(client)
    tid = client.post("/guest/transcriptions/jobs", headers=headers, files={"file": ("test.wav", wav_bytes)}).json()["id"]
    db = db_context["session_factory"]()
    db.query(GuestSession).one().expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert apply_guest_retention(db, apply=True)["active_preserved"] == 1
    row = db.get(Transcription, tid)
    row.status = row.job.status = "failed"
    db.commit()
    assert apply_guest_retention(db)["candidates"] == 1
    assert db.get(Transcription, tid) is not None
    assert apply_guest_retention(db, apply=True)["transcriptions_deleted"] == 1
    assert apply_guest_retention(db, apply=True)["transcriptions_deleted"] == 0
    assert db.query(GuestSession).count() == 0
    db.close()


def test_guest_upload_body_is_bounded_before_multipart_parsing(db_context, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_MAX_UPLOAD_MB", 1)
    response = db_context["client"].post("/guest/transcriptions/jobs",
        content=b"x" * (2 * 1024 * 1024), headers={"Content-Type": "multipart/form-data; boundary=test"})
    assert response.status_code == 413
    assert db_context["queue"].enqueued == []


def test_guest_global_budget_is_shared_with_public_accounts(db_context, monkeypatch, wav_bytes):
    client = db_context["client"]
    redis = FakeRedisConnection()
    monkeypatch.setattr(rate_limit, "get_redis_connection", lambda: redis)
    monkeypatch.setattr(settings, "PUBLIC_JOB_RATE_LIMIT_GLOBAL", 1)
    guest = guest_headers(client)
    public = signup(client).json()
    headers = {"Authorization": "Bearer " + public["access_token"]}
    assert client.post("/guest/transcriptions/jobs", headers=guest,
        files={"file": ("test.wav", wav_bytes)}).status_code == 202
    assert client.post("/transcriptions/jobs", headers=headers,
        files={"file": ("test.wav", wav_bytes)}).status_code == 429
    assert len(db_context["queue"].enqueued) == 1


def test_public_account_upload_is_bounded_before_multipart_parsing(db_context, monkeypatch):
    client = db_context["client"]
    token = signup(client).json()["access_token"]
    monkeypatch.setattr(settings, "PUBLIC_MAX_UPLOAD_MB", 1)
    response = client.post("/transcriptions/jobs", content=b"x" * (2 * 1024 * 1024),
        headers={"Authorization": "Bearer " + token, "Content-Type": "multipart/form-data; boundary=test"})
    assert response.status_code == 413
    assert db_context["queue"].enqueued == []


@pytest.mark.parametrize("route", ["/auth/signup", "/auth/login", "/guest/claim"])
def test_sensitive_json_bodies_are_bounded_before_parsing(db_context, route):
    response = db_context["client"].post(route, content=b"x" * (17 * 1024),
                                         headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    db = db_context["session_factory"]()
    assert db.query(User).count() == 2  # Only the pre-existing synthetic seed.
    db.close()


def test_deletion_does_not_report_missing_input_as_cleanup_failure(db_context, wav_bytes, caplog):
    client = db_context["client"]
    guest = guest_headers(client)
    tid = client.post("/guest/transcriptions/jobs", headers=guest,
                      files={"file": ("test.wav", wav_bytes)}).json()["id"]
    db = db_context["session_factory"]()
    row = db.get(Transcription, tid)
    row.status = row.job.status = "failed"
    from pathlib import Path
    (db_context["tmp_path"] / "uploads" / row.job.input_object_key).unlink()
    db.commit()
    assert client.delete(f"/guest/transcriptions/{tid}", headers=guest).status_code == 200
    assert "Input cleanup incomplete" not in caplog.text
    db.close()


def test_claimed_result_survives_guest_retention_and_preserves_job_limits(db_context, auth_headers, wav_bytes):
    client = db_context["client"]
    guest = guest_headers(client)
    tid = client.post("/guest/transcriptions/jobs", headers=guest, files={"file": ("test.wav", wav_bytes)}).json()["id"]
    assert client.post("/guest/claim", headers=auth_headers(), json={"guest_token": guest["Authorization"][7:]}).status_code == 200
    db = db_context["session_factory"]()
    session = db.query(GuestSession).one()
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    row = db.get(Transcription, tid)
    row.status = row.job.status = "completed"
    db.commit()
    assert apply_guest_retention(db, apply=True)["transcriptions_deleted"] == 0
    assert db.get(Transcription, tid).job.max_duration_seconds == settings.PUBLIC_MAX_AUDIO_SECONDS
    assert db.query(GuestSession).count() == 0
    db.close()


def test_guest_retention_reports_partial_file_failure(db_context, monkeypatch, wav_bytes):
    from src.services.object_storage import LocalObjectStorage, StorageError
    client = db_context["client"]
    guest = guest_headers(client)
    tid = client.post("/guest/transcriptions/jobs", headers=guest, files={"file": ("test.wav", wav_bytes)}).json()["id"]
    db = db_context["session_factory"]()
    db.query(GuestSession).one().expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    row = db.get(Transcription, tid)
    row.status = row.job.status = "failed"
    db.commit()
    def fail_delete(_self, _key):
        raise StorageError("Synthetic deletion failure")
    monkeypatch.setattr(LocalObjectStorage, "delete", fail_delete)
    report = apply_guest_retention(db, apply=True)
    assert report["transcriptions_deleted"] == report["files_failed"] == 1
    assert apply_guest_retention(db, apply=True)["candidates"] == 0
    db.close()
