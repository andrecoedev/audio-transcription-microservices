"""Verified Firebase password identities share the existing internal domain."""
import time

import pytest
from fastapi import HTTPException

from src.config import settings
from src.models import FirebaseIdentity, User
from src.routers import auth
from src.security import create_access_token, get_password_hash
from src.services import firebase_identity
from .test_firebase_auth import PROJECT, _claims


@pytest.fixture(autouse=True)
def enable_password(monkeypatch):
    monkeypatch.setattr(settings, 'FIREBASE_AUTH_ENABLED', True)
    monkeypatch.setattr(settings, 'FIREBASE_PASSWORD_ENABLED', True)
    monkeypatch.setattr(settings, 'FIREBASE_PROJECT_ID', PROJECT)
    monkeypatch.delenv('FIREBASE_AUTH_EMULATOR_HOST', raising=False)


def password_identity(monkeypatch, **changes):
    claims = _claims(firebase={'sign_in_provider': 'password'}, auth_time=int(time.time()), **changes)
    monkeypatch.setattr(firebase_identity, '_verify_with_sdk', lambda _token: claims)
    return firebase_identity.verify_firebase_token('synthetic-id-proof')


def test_password_claims_require_server_verified_email(monkeypatch):
    identity = password_identity(monkeypatch)
    assert identity.sign_in_provider == 'password'
    assert identity.google_connected is False
    with pytest.raises(HTTPException) as failure:
        password_identity(monkeypatch, email_verified=False)
    assert failure.value.status_code == 401


def test_disabled_password_fails_closed_but_google_still_works(monkeypatch):
    monkeypatch.setattr(settings, 'FIREBASE_PASSWORD_ENABLED', False)
    with pytest.raises(HTTPException) as failure:
        password_identity(monkeypatch)
    assert failure.value.status_code == 401
    monkeypatch.setattr(firebase_identity, '_verify_with_sdk', lambda _token: _claims())
    assert firebase_identity.verify_firebase_token('synthetic-google-proof').sign_in_provider == 'google.com'


def test_unverified_password_cannot_create_user_or_access_domain(db_context, monkeypatch):
    monkeypatch.setattr(firebase_identity, '_verify_with_sdk', lambda _token:
                        _claims(email_verified=False, firebase={'sign_in_provider': 'password'}))
    headers = {'Authorization': 'Bearer synthetic-unverified-proof'}
    assert db_context['client'].post('/auth/firebase', headers=headers).status_code == 401
    assert db_context['client'].get('/auth/me', headers=headers).status_code == 401
    with db_context['session_factory']() as db:
        assert db.query(User).count() == 2
        assert db.query(FirebaseIdentity).count() == 0


def test_password_login_is_idempotent_and_does_not_claim_google(db_context, monkeypatch):
    identity = password_identity(monkeypatch)
    monkeypatch.setattr(auth, 'verify_firebase_token', lambda _token: identity)
    headers = {'Authorization': 'Bearer synthetic-password-proof'}
    first = db_context['client'].post('/auth/firebase', headers=headers)
    second = db_context['client'].post('/auth/firebase', headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()['user']['id'] == second.json()['user']['id']
    assert first.json()['user']['google_connected'] is False
    assert first.json()['user']['firebase_sign_in_provider'] == 'password'
    me = db_context['client'].get('/auth/me', headers=headers)
    assert me.status_code == 200
    assert me.json()['user']['google_connected'] is False
    assert me.json()['user']['firebase_email'] == identity.email
    with db_context['session_factory']() as db:
        user = db.get(User, first.json()['user']['id'])
        assert user.hashed_password is None
        assert user.plan == 'free'
        assert not user.is_superuser


def test_legacy_password_link_preserves_id_plan_and_local_login(db_context, monkeypatch):
    with db_context['session_factory']() as db:
        user = db.get(User, 1)
        user.hashed_password = get_password_hash('synthetic-local-password')
        user.plan = 'starter'
        db.commit()
    identity = password_identity(monkeypatch, email='alice@example.test')
    monkeypatch.setattr(auth, 'verify_firebase_token', lambda _token: identity)
    headers = {'Authorization': 'Bearer synthetic-password-proof'}
    assert db_context['client'].post('/auth/firebase', headers=headers).status_code == 409
    local_token = create_access_token({'sub': '1', 'username': 'alice'})
    request = {'id_token': 'synthetic-password-proof', 'password': 'synthetic-local-password'}
    local_headers = {'Authorization': f'Bearer {local_token}'}
    for _ in range(2):
        linked = db_context['client'].post('/auth/firebase/link', headers=local_headers, json=request)
        assert linked.status_code == 200
        assert linked.json()['user']['id'] == 1
    with db_context['session_factory']() as db:
        assert db.get(User, 1).plan == 'starter'
        assert db.get(User, 1).hashed_password is not None
        assert db.query(User).count() == 2
        assert db.query(FirebaseIdentity).count() == 1


def test_google_and_password_same_uid_resolve_same_internal_user(db_context, monkeypatch):
    password_identity(monkeypatch)
    headers = {'Authorization': 'Bearer synthetic-id-proof'}
    first = db_context['client'].post('/auth/firebase', headers=headers)
    monkeypatch.setattr(firebase_identity, '_verify_with_sdk', lambda _token: _claims())
    google = db_context['client'].post('/auth/firebase', headers=headers)
    assert first.status_code == google.status_code == 200
    assert first.json()['user']['id'] == google.json()['user']['id']
    assert google.json()['user']['google_connected'] is True


def test_verified_access_email_does_not_overwrite_internal_profile(db_context, monkeypatch):
    with db_context['session_factory']() as db:
        db.add(FirebaseIdentity(project_id=PROJECT, uid='synthetic-google-uid', user_id=1))
        db.commit()
    password_identity(monkeypatch, email='access@example.test')
    response = db_context['client'].get('/auth/me', headers={'Authorization': 'Bearer synthetic-id-proof'})
    assert response.status_code == 200
    assert response.json()['user']['email'] == 'alice@example.test'
    assert response.json()['user']['firebase_email'] == 'access@example.test'
