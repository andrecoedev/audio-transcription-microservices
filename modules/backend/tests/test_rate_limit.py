"""Rate limiting remains atomic and fails closed before authentication/upload work."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.config import settings
from src.database import get_db
from src.routers import auth
from src.services import rate_limit

from .conftest import FakeRedisConnection


def test_job_creation_limit_returns_429_without_storing_second_upload(
    db_context, auth_headers, wav_bytes, monkeypatch
):
    connection = FakeRedisConnection()
    monkeypatch.setattr(rate_limit, "get_redis_connection", lambda: connection)
    monkeypatch.setattr(settings, "JOB_RATE_LIMIT_PER_USER", 1)
    first = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("first.wav", wav_bytes, "audio/wav")},
        headers=auth_headers(),
    )
    second = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("second.wav", wav_bytes, "audio/wav")},
        headers=auth_headers(),
    )
    assert first.status_code == 202
    assert second.status_code == 429
    assert second.headers["retry-after"].isdigit()
    assert len(db_context["queue"].enqueued) == 1
    assert len(list((db_context["tmp_path"] / "uploads").iterdir())) == 1


def test_upload_limit_rejects_other_user_from_same_ip(
    db_context, auth_headers, wav_bytes, monkeypatch
):
    connection = FakeRedisConnection()
    monkeypatch.setattr(rate_limit, "get_redis_connection", lambda: connection)
    monkeypatch.setattr(settings, "UPLOAD_RATE_LIMIT_PER_IP", 1)
    first = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("first.wav", wav_bytes, "audio/wav")},
        headers=auth_headers(username="alice"),
    )
    second = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("second.wav", wav_bytes, "audio/wav")},
        headers=auth_headers(username="bob"),
    )
    assert first.status_code == 202
    assert second.status_code == 429
    malformed = db_context["client"].post(
        "/transcriptions/jobs",
        data=b"not multipart",
        headers={**auth_headers(username="bob"), "Content-Type": "text/plain"},
    )
    assert malformed.status_code == 429


def test_login_limit_prevents_repeated_password_checks(db_context, monkeypatch):
    connection = FakeRedisConnection()
    monkeypatch.setattr(rate_limit, "get_redis_connection", lambda: connection)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_PER_ACCOUNT", 1)
    app = FastAPI()
    app.include_router(auth.router)
    app.dependency_overrides[get_db] = lambda: db_context["session_factory"]()
    with TestClient(app) as client:
        first = client.post("/auth/login", json={"username": "missing", "password": "bad"})
        second = client.post("/auth/login", json={"username": "missing", "password": "bad"})
    assert first.status_code == 401
    assert second.status_code == 429


def test_redis_failure_closes_login_and_upload_without_leaking_error(
    db_context, auth_headers, wav_bytes, monkeypatch, caplog
):
    def unavailable():
        raise RuntimeError("redis://private-password@internal:6379")

    monkeypatch.setattr(rate_limit, "get_redis_connection", unavailable)
    app = FastAPI()
    app.include_router(auth.router)
    app.dependency_overrides[get_db] = lambda: db_context["session_factory"]()
    with TestClient(app) as client:
        login = client.post("/auth/login", json={"username": "alice", "password": "bad"})
    upload = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("meeting.wav", wav_bytes, "audio/wav")},
        headers=auth_headers(),
    )
    assert login.status_code == upload.status_code == 503
    assert "private-password" not in login.text + upload.text
    assert "private-password" not in caplog.text
    assert not db_context["queue"].enqueued
