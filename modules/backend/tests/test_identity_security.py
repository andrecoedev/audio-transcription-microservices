import base64
from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
import jwt

from src.config import Settings, settings
from src.database import get_db
from src.models import AuditEvent, Transcription, TranscriptionOwnership, User
from src.routers import api_keys, auth
from src.security import create_access_token, decode_access_token, get_password_hash, verify_password


def _app_for(factory, *routers):
    app = FastAPI()
    for router in routers:
        app.include_router(router.router)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return app


def test_login_creates_persistent_admin_and_stable_subject(db_context, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "AUTH_ADMIN_EMAIL", "admin@example.test")
    monkeypatch.setattr(settings, "AUTH_ADMIN_PASSWORD", "correct horse battery staple")
    monkeypatch.setattr(settings, "AUTH_ADMIN_PASSWORD_HASH", None)
    app = _app_for(db_context["session_factory"], auth)

    with TestClient(app) as client:
        response = client.post(
            "/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        )
    assert response.status_code == 200

    db = db_context["session_factory"]()
    try:
        user = db.query(User).filter_by(username="admin").one()
        assert user.email == "admin@example.test"
        assert user.hashed_password != "correct horse battery staple"
        assert verify_password("correct horse battery staple", user.hashed_password)
        token_data = decode_access_token(response.json()["access_token"])
        assert token_data.user_id == user.id
        assert token_data.username == "admin"
        assert db.query(AuditEvent).filter_by(event="user.login").count() == 1
    finally:
        db.close()


def test_login_rejects_wrong_password_for_persistent_user(db_context):
    db = db_context["session_factory"]()
    db.query(User).filter_by(username="alice").one().hashed_password = get_password_hash("right")
    db.commit()
    db.close()
    app = _app_for(db_context["session_factory"], auth)
    with TestClient(app) as client:
        response = client.post("/auth/login", json={"username": "alice", "password": "wrong"})
    assert response.status_code == 401


def test_password_hash_is_not_reversible_plaintext():
    password = "a long unique password"
    hashed = get_password_hash(password)
    assert password not in hashed
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)


def test_expired_and_invalid_signature_tokens_are_rejected(db_context):
    app = _app_for(db_context["session_factory"], auth)
    expired = create_access_token(
        {"sub": "1", "username": "alice", "roles": ["user"], "scopes": []},
        expires_delta=timedelta(seconds=-1),
    )
    invalid = jwt.encode(
        {
            "sub": "1",
            "username": "alice",
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        },
        "different-signing-secret-with-enough-entropy",
        algorithm=settings.ALGORITHM,
    )
    with TestClient(app) as client:
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {invalid}"}).status_code == 401


def test_deeply_nested_unsigned_payload_is_rejected_before_json_parsing(db_context):
    """Keep verification enabled: GHSA-42vr-xj54-vc7v affects pre-verification parsing."""
    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    header = encode(b'{"alg":"HS256","typ":"JWT"}')
    payload = encode(b"[" * 20000 + b"]" * 20000)
    token = ".".join((header, payload, encode(b"forged-signature")))
    assert decode_access_token(token) is None
    app = _app_for(db_context["session_factory"], auth)
    with TestClient(app) as client:
        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "RecursionError" not in response.text


def test_production_rejects_wildcard_cors_and_insecure_auth():
    candidate = Settings(
        APP_ENV="prod",
        DATABASE_URL="postgresql+psycopg://user:pass@db/app",
        SECRET_KEY="strong-production-secret-with-at-least-32-characters",
        AUTH_ADMIN_PASSWORD_HASH="$2b$12$abcdefghijklmnopqrstuuuuuuuuuuuuuuuuuuuuuuuuuuuuu",
        CORS_ALLOWED_ORIGINS="*",
        AUTH_MODE="permissive",
        AUTH_ALLOW_DEMO_LOGIN=True,
    )
    errors = candidate.validate_startup()
    assert any("cannot contain '*'" in error for error in errors)
    assert any("AUTH_MODE" in error for error in errors)
    assert any("AUTH_ALLOW_DEMO_LOGIN" in error for error in errors)


def test_provider_credentials_are_environment_only_and_never_returned(db_context, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "HF_TOKEN", "hf_super_secret")
    db = db_context["session_factory"]()
    db.get(User, 1).is_superuser = True
    db.commit()
    db.close()
    app = _app_for(db_context["session_factory"], api_keys)
    headers = auth_headers(roles=["admin"], scopes=["manage_keys"])
    with TestClient(app) as client:
        status_response = client.get("/api-keys", headers=headers)
        retired_response = client.post("/api-keys", headers=headers)
    assert status_response.status_code == 200
    serialized = status_response.text
    assert "hf_super_secret" not in serialized
    assert status_response.json()["source"] == "environment"
    assert retired_response.status_code == 410


def test_exact_legacy_owner_is_reconciled_on_login(db_context):
    db = db_context["session_factory"]()
    user = db.query(User).filter_by(username="alice").one()
    user.hashed_password = get_password_hash("right")
    transcription = Transcription(
        filename="legacy.wav",
        original_filename="legacy.wav",
        file_size_mb=1,
        duration_seconds=1,
        transcription_model="whisper",
        segments=[],
        status="completed",
    )
    db.add(transcription)
    db.flush()
    db.add(TranscriptionOwnership(transcription_id=transcription.id, owner_sub="alice"))
    db.commit()
    transcription_id = transcription.id
    db.close()

    app = _app_for(db_context["session_factory"], auth)
    with TestClient(app) as client:
        assert client.post(
            "/auth/login", json={"username": "alice", "password": "right"}
        ).status_code == 200
    check = db_context["session_factory"]()
    owner = check.query(TranscriptionOwnership).filter_by(
        transcription_id=transcription_id
    ).one()
    assert owner.user_id == 1
    check.close()
