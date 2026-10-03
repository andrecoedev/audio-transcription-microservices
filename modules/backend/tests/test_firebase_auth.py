"""Firebase authentication boundaries with synthetic verified claims only."""
import time
import secrets
from cryptography.fernet import Fernet

from fastapi import HTTPException
import pytest

from src.config import settings
from src.models import AuditEvent, FirebaseIdentity, GuestSession, User, Transcription, TranscriptionOwnership
from src.routers import auth
from src.security import create_access_token, get_password_hash
from src.services import firebase_identity
from src.services.firebase_identity import VerifiedFirebaseIdentity


PROJECT = "synthetic-project-123"


def _claims(**changes):
    claims = {
        "aud": PROJECT,
        "iss": f"https://securetoken.google.com/{PROJECT}",
        "sub": "synthetic-google-uid",
        "uid": "synthetic-google-uid",
        "email": "google@example.test",
        "email_verified": True,
        "firebase": {"sign_in_provider": "google.com", "tenant": None},
        "auth_time": 1_800_000_000,
        "name": "Synthetic Google User",
    }
    claims.update(changes)
    return claims


def _identity(uid="synthetic-google-uid", email="google@example.test", auth_time=None):
    return VerifiedFirebaseIdentity(
        project_id=PROJECT,
        uid=uid,
        email=email,
        auth_time=int(time.time()) if auth_time is None else auth_time,
        display_name="Synthetic Google User",
    )


@pytest.fixture(autouse=True)
def firebase_settings(monkeypatch):
    monkeypatch.setattr(settings, "FIREBASE_AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", PROJECT)
    monkeypatch.setattr(settings, "AUTH_ADMIN_EMAIL", "admin@example.test")
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)


def test_verified_claims_are_checked_and_email_is_normalized(monkeypatch):
    seen = []
    monkeypatch.setattr(firebase_identity, "_verify_with_sdk", lambda token: seen.append(token) or _claims(email="Google@Example.Test"))

    identity = firebase_identity.verify_firebase_token("synthetic-signed-token")

    assert seen == ["synthetic-signed-token"]
    assert identity.project_id == PROJECT
    assert identity.uid == "synthetic-google-uid"
    assert identity.email == "google@example.test"
    assert identity.auth_time == 1_800_000_000
    assert identity.display_name == "Synthetic Google User"


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "another-project"},
        {"iss": "https://securetoken.google.com/another-project"},
        {"sub": "different-uid"},
        {"uid": ""},
        {"email_verified": False},
        {"email": "not-an-email"},
        {"firebase": {"sign_in_provider": "password", "tenant": None}},
        {"firebase": {"sign_in_provider": "google.com", "tenant": "tenant-id"}},
        {"auth_time": True},
    ],
)
def test_unacceptable_verified_claims_are_rejected(monkeypatch, changes):
    monkeypatch.setattr(firebase_identity, "_verify_with_sdk", lambda _token: _claims(**changes))

    with pytest.raises(HTTPException) as error:
        firebase_identity.verify_firebase_token("synthetic-signed-token")

    assert error.value.status_code == 401


def test_firebase_login_creates_passwordless_user_and_stable_uid_binding(db_context, monkeypatch):
    monkeypatch.setattr(auth, "verify_firebase_token", lambda _token: _identity())

    response = db_context["client"].post(
        "/auth/firebase", headers={"Authorization": "Bearer synthetic-id-token"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["user"]["email"] == "google@example.test"
    assert body["user"]["auth_provider"] == "firebase"
    assert body["user"]["google_connected"] is True
    db = db_context["session_factory"]()
    try:
        user = db.query(User).filter_by(email="google@example.test").one()
        binding = db.get(FirebaseIdentity, (PROJECT, "synthetic-google-uid"))
        assert binding.user_id == user.id == body["user"]["id"]
        assert user.hashed_password is None
        assert user.registration_source == "public"
        assert db.query(AuditEvent).filter_by(event="user.registered", actor_user_id=user.id).count() == 1
    finally:
        db.close()


def test_bound_uid_resolves_existing_internal_user_id_without_replacing_account(db_context, monkeypatch):
    db = db_context["session_factory"]()
    original_hash = get_password_hash("synthetic-local-password")
    user = db.get(User, 1)
    user.hashed_password = original_hash
    user.email = "alice@example.test"
    db.add(FirebaseIdentity(project_id=PROJECT, uid="bound-google-uid", user_id=user.id))
    db.commit()
    db.close()
    monkeypatch.setattr(auth, "verify_firebase_token", lambda _token: _identity("bound-google-uid", "different@example.test"))

    response = db_context["client"].post(
        "/auth/firebase", headers={"Authorization": "Bearer synthetic-id-token"}
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == 1
    check = db_context["session_factory"]()
    try:
        user = check.get(User, 1)
        assert user.email == "alice@example.test"
        assert user.hashed_password == original_hash
        assert check.query(User).count() == 2
    finally:
        check.close()


def test_firebase_bearer_auth_uses_bound_internal_user(db_context, monkeypatch):
    db = db_context["session_factory"]()
    db.add(FirebaseIdentity(project_id=PROJECT, uid="bound-google-uid", user_id=1))
    db.commit()
    db.close()
    monkeypatch.setattr(
        firebase_identity,
        "verify_firebase_token",
        lambda _token: _identity("bound-google-uid", "alice@example.test"),
    )

    response = db_context["client"].get(
        "/auth/me", headers={"Authorization": "Bearer synthetic-id-token"}
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == 1
    assert response.json()["user"]["auth_provider"] == "firebase"
    assert response.json()["user"]["google_connected"] is True


def test_matching_email_does_not_automatically_link_google_identity(db_context, monkeypatch):
    monkeypatch.setattr(auth, "verify_firebase_token", lambda _token: _identity(email="alice@example.test"))

    response = db_context["client"].post(
        "/auth/firebase", headers={"Authorization": "Bearer synthetic-id-token"}
    )

    assert response.status_code == 409
    assert "existing USAGI account" in response.json()["detail"]
    db = db_context["session_factory"]()
    try:
        assert db.get(User, 1).email == "alice@example.test"
        assert db.query(FirebaseIdentity).count() == 0
        assert db.query(User).count() == 2
    finally:
        db.close()


@pytest.mark.parametrize("failure", ["invalid", "expired"])
def test_invalid_or_expired_firebase_tokens_are_rejected_without_sdk_credentials(db_context, monkeypatch, failure):
    def reject(_token):
        raise HTTPException(401, f"synthetic {failure} token")

    monkeypatch.setattr(firebase_identity, "_verify_with_sdk", reject)

    response = db_context["client"].post(
        "/auth/firebase", headers={"Authorization": "Bearer synthetic-id-token"}
    )

    assert response.status_code == 401
    assert db_context["session_factory"]().query(FirebaseIdentity).count() == 0


def test_link_requires_local_password_and_recent_google_authentication(db_context, monkeypatch):
    db = db_context["session_factory"]()
    user = db.get(User, 1)
    user.hashed_password = get_password_hash("synthetic-local-password")
    db.commit()
    db.close()
    monkeypatch.setattr(auth, "verify_firebase_token", lambda _token: _identity())
    local_token = create_access_token({"sub": "1", "username": "alice", "scopes": [], "roles": []})
    headers = {"Authorization": f"Bearer {local_token}"}

    denied = db_context["client"].post(
        "/auth/firebase/link",
        headers=headers,
        json={"id_token": "synthetic-id-token", "password": "wrong-password"},
    )
    assert denied.status_code == 401

    linked = db_context["client"].post(
        "/auth/firebase/link",
        headers=headers,
        json={"id_token": "synthetic-id-token", "password": "synthetic-local-password"},
    )

    assert linked.status_code == 200
    assert linked.json()["user"]["id"] == 1
    check = db_context["session_factory"]()
    try:
        assert check.get(FirebaseIdentity, (PROJECT, "synthetic-google-uid")).user_id == 1
        assert check.query(AuditEvent).filter_by(event="user.identity_linked", actor_user_id=1).count() == 1
    finally:
        check.close()

    monkeypatch.setattr(auth, "verify_firebase_token", lambda _token: _identity(auth_time=int(time.time()) - 301))
    stale = db_context["client"].post(
        "/auth/firebase/link",
        headers=headers,
        json={"id_token": "synthetic-id-token", "password": "synthetic-local-password"},
    )
    assert stale.status_code == 401


def test_guest_session_remains_usable_with_firebase_auth_enabled(db_context):
    started = db_context["client"].post("/guest/sessions")

    assert started.status_code == 201
    guest_token = started.json()["guest_token"]
    current = db_context["client"].get(
        "/guest/session", headers={"Authorization": f"Bearer {guest_token}"}
    )

    assert current.status_code == 200
    assert "expires_at" in current.json()
    assert db_context["session_factory"]().query(GuestSession).count() == 1


def test_new_firebase_user_cannot_access_existing_account_preferences(db_context, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, 'PROVIDER_CREDENTIAL_ENCRYPTION_KEY', Fernet.generate_key().decode())
    assert db_context['client'].post('/settings/providers/gemini/credential',
        headers=auth_headers(), json={'secret': secrets.token_urlsafe(32)}).status_code == 200
    db = db_context['session_factory']()
    transcription = Transcription(filename='synthetic.wav', original_filename='synthetic.wav',
        file_size_mb=0.1, duration_seconds=1, transcription_model='whisper', status='completed')
    db.add(transcription)
    db.flush()
    resource_id = transcription.id
    db.add(TranscriptionOwnership(transcription_id=resource_id, user_id=1, owner_sub='alice'))
    db.commit()
    db.close()
    monkeypatch.setattr(auth, 'verify_firebase_token', lambda _token: _identity())
    response = db_context['client'].post('/auth/firebase', headers={'Authorization': 'Bearer synthetic-id-proof'})
    internal_id = response.json()['user']['id']
    monkeypatch.setattr(firebase_identity, 'verify_firebase_token', lambda _token: _identity())
    headers = {'Authorization': 'Bearer synthetic-id-proof'}
    settings_response = db_context['client'].get('/settings/providers', headers=headers)
    assert settings_response.status_code == 200
    assert settings_response.json()['credentials']['gemini']['configured'] is False
    assert internal_id not in (1, 2)
    assert db_context['client'].get(f'/transcriptions/{resource_id}', headers=headers).status_code == 404
    assert db_context['client'].get('/settings/providers', headers=auth_headers()).json()['credentials']['gemini']['configured'] is True


def test_signup_disabled_only_when_google_enabled(db_context, monkeypatch):
    assert db_context['client'].get('/auth/config').json()['local_signup_enabled'] is False
    result = db_context['client'].post('/auth/signup', json={
        'username': 'synthetic-new-account', 'email': 'new@example.test', 'password': 'synthetic long password',
    })
    assert result.status_code == 409
    monkeypatch.setattr(settings, 'FIREBASE_AUTH_ENABLED', False)
    assert db_context['client'].get('/auth/config').json()['local_signup_enabled'] is True


def test_emulator_configuration_is_rejected_before_verification(monkeypatch):
    monkeypatch.setenv('FIREBASE_AUTH_EMULATOR_HOST', 'localhost:9099')
    monkeypatch.setattr(firebase_identity, '_verify_with_sdk', lambda token: pytest.fail('must fail closed'))
    with pytest.raises(HTTPException) as error:
        firebase_identity.verify_firebase_token('synthetic-unsigned-emulator-proof')
    assert error.value.status_code == 503
