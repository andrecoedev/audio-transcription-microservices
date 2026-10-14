"""Account data is returned only to its authenticated internal owner."""
from .test_privacy_lifecycle import _seed_owned_data
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from src.models import AuditEvent, Transcription, UserProviderPreferences, UsageEvent
import pytest

from .conftest import FakeRedisConnection
from src.security import get_password_hash
from src.models import AccountDeletion, FirebaseIdentity, Meeting, MeetingIntelligence, User, UserProviderCredential
from src.services import account_deletion, firebase_identity
from src.services.firebase_identity import VerifiedFirebaseIdentity
import time


def test_account_deletion_requires_password_and_erases_only_owner(db_context, auth_headers):
    password = secrets.token_urlsafe(16)
    own = _seed_owned_data(db_context["session_factory"], db_context["tmp_path"] / "own.wav")
    other = _seed_owned_data(db_context["session_factory"], db_context["tmp_path"] / "other.wav", user_id=2, username="bob")
    db = db_context["session_factory"]()
    db.get(User, 1).hashed_password = get_password_hash(password)
    db.commit()
    db.close()
    client, headers = db_context["client"], auth_headers()
    assert client.request("DELETE", "/account?user_id=2", headers=headers,
        json={"confirmation": "EXCLUIR", "password": password}).status_code == 422
    assert client.request("DELETE", "/account", headers=headers,
        json={"confirmation": "EXCLUIR", "password": password, "user_id": 2}).status_code == 422
    refused = client.request("DELETE", "/account", headers=headers,
                             json={"confirmation": "EXCLUIR", "password": "synthetic-wrong-password"})
    assert refused.status_code == 403
    result = client.request("DELETE", "/account", headers=headers,
                            json={"confirmation": "EXCLUIR", "password": password})
    assert result.status_code == 200
    assert result.json()["account_deleted"] is True
    db = db_context["session_factory"]()
    assert db.get(User, 1) is None
    assert db.get(User, 2) is not None
    assert db.get(Transcription, own) is None
    assert db.get(Transcription, other) is not None
    db.close()
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_deleted_bootstrap_admin_is_not_recreated_from_environment(db_context, auth_headers, monkeypatch):
    from src.config import settings
    password = secrets.token_urlsafe(16)
    monkeypatch.setattr(settings, "AUTH_ADMIN_USERNAME", "alice")
    monkeypatch.setattr(settings, "AUTH_ADMIN_PASSWORD", password)
    monkeypatch.setattr(settings, "AUTH_ADMIN_PASSWORD_HASH", None)
    db = db_context["session_factory"]()
    db.get(User, 1).hashed_password = get_password_hash(password)
    db.get(User, 1).is_superuser = True
    db.commit()
    db.close()
    client = db_context["client"]
    assert client.request("DELETE", "/account", headers=auth_headers(), json={"confirmation": "EXCLUIR", "password": password}).status_code == 200
    assert client.post("/auth/login", json={"username": "alice", "password": password}).status_code == 401
    db = db_context["session_factory"]()
    assert db.query(AccountDeletion).one().blocks_bootstrap is True
    assert db.get(User, 1) is None
    db.close()


def test_firebase_deletion_is_durable_and_blocks_pending_identity_reprovision(db_context, monkeypatch, caplog):
    from src.config import settings
    monkeypatch.setattr(settings, "FIREBASE_AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", "synthetic-project-123")
    identity = VerifiedFirebaseIdentity("synthetic-project-123", "synthetic-uid", "alice@example.test", int(time.time()))
    monkeypatch.setattr(firebase_identity, "verify_firebase_token", lambda _token: identity)
    from src.routers import privacy
    monkeypatch.setattr(privacy, "verify_firebase_token", lambda _token: identity)
    canary = secrets.token_urlsafe(24)
    def unavailable(*_args):
        raise RuntimeError(canary)
    monkeypatch.setattr(account_deletion, "delete_firebase_identity", unavailable)
    db = db_context["session_factory"]()
    db.add(FirebaseIdentity(project_id=identity.project_id, uid=identity.uid, user_id=1))
    db.add(UserProviderCredential(id=str(uuid4()), user_id=1, provider="gemini", ciphertext=canary))
    db.commit()
    db.close()
    headers = {"Authorization": "Bearer synthetic-firebase-token"}
    response = db_context["client"].request("DELETE", "/account", headers=headers, json={"confirmation": "EXCLUIR"})
    assert response.status_code == 200
    assert response.json()["identity_cleanup_pending"] is True
    assert canary not in response.text and canary not in caplog.text
    db = db_context["session_factory"]()
    assert db.get(User, 1) is None
    assert db.query(UserProviderCredential).count() == 0
    assert db.query(FirebaseIdentity).count() == 0
    receipt = db.query(AccountDeletion).one()
    assert receipt.attempts == 1 and receipt.firebase_uid == identity.uid
    with pytest.raises(Exception) as error:
        firebase_identity.resolve_firebase_user(db, identity)
    assert error.value.status_code == 410
    assert db.query(User).count() == 1  # Only Bob survives; never provision Alice again.
    # A different local account must not relink the pending-deletion UID.
    from src.routers import auth
    password = secrets.token_urlsafe(16)
    db.get(User, 2).hashed_password = get_password_hash(password)
    db.commit()
    monkeypatch.setattr(auth, "verify_firebase_token", lambda _token: identity)
    from src.security import create_access_token
    other_headers = {"Authorization": "Bearer " + create_access_token({"sub": "2", "username": "bob"})}
    linked = db_context["client"].post("/auth/firebase/link", headers=other_headers,
        json={"id_token": "synthetic-id-token", "password": password})
    assert linked.status_code == 410
    assert db.query(FirebaseIdentity).count() == 0
    assert account_deletion.retry_identity_cleanup(db)["dry_run"] is True
    calls = []
    monkeypatch.setattr(account_deletion, "delete_firebase_identity", lambda project, uid: calls.append((project, uid)))
    assert account_deletion.retry_identity_cleanup(db, apply=True)["completed"] == 1
    db.expire_all()
    assert db.query(AccountDeletion).one().firebase_uid is None
    assert db.query(AccountDeletion).one().firebase_project_id is None
    assert account_deletion.retry_identity_cleanup(db, apply=True)["candidates"] == 0
    assert calls == [(identity.project_id, identity.uid)]
    db.close()


@pytest.mark.parametrize("age", [301, -60])
def test_account_deletion_rejects_stale_or_future_firebase_auth(db_context, monkeypatch, age):
    from src.config import settings
    from src.routers import privacy
    monkeypatch.setattr(settings, "FIREBASE_AUTH_ENABLED", True)
    identity = VerifiedFirebaseIdentity("synthetic-project-123", "synthetic-uid", "alice@example.test", int(time.time()) - age)
    db = db_context["session_factory"]()
    db.add(FirebaseIdentity(project_id=identity.project_id, uid=identity.uid, user_id=1))
    db.commit()
    db.close()
    monkeypatch.setattr(firebase_identity, "verify_firebase_token", lambda _token: identity)
    monkeypatch.setattr(privacy, "verify_firebase_token", lambda _token: identity)
    response = db_context["client"].request("DELETE", "/account", headers={"Authorization": "Bearer synthetic-id-token"}, json={"confirmation": "EXCLUIR"})
    assert response.status_code == 403
    db = db_context["session_factory"]()
    assert db.get(User, 1) is not None and db.query(AccountDeletion).count() == 0
    db.close()


@pytest.mark.parametrize("kind", ["transcription", "intelligence", "legacy"])
def test_account_deletion_blocks_active_processing(db_context, auth_headers, kind):
    password = secrets.token_urlsafe(16)
    resource = _seed_owned_data(db_context["session_factory"], db_context["tmp_path"] / "own.wav")
    db = db_context["session_factory"]()
    db.get(User, 1).hashed_password = get_password_hash(password)
    transcription = db.get(Transcription, resource)
    if kind == "transcription":
        transcription.job.status = "processing"
    elif kind == "intelligence":
        db.add(Meeting(id=resource, title="Synthetic", language="pt"))
        db.flush()
        db.add(MeetingIntelligence(meeting_id=resource, revision=1, schema_version="1", provider="gemini", model="synthetic", status="processing", source_metadata={}, input_fingerprint="synthetic"))
    else:
        db_context["queue"].enqueue("synthetic", resource, job_id=f"meeting_minutes_{resource}_synthetic")
    db.commit()
    db.close()
    response = db_context["client"].request("DELETE", "/account", headers=auth_headers(), json={"confirmation": "EXCLUIR", "password": password})
    assert response.status_code == 409
    db = db_context["session_factory"]()
    assert db.get(User, 1) is not None and db.get(Transcription, resource) is not None
    assert db.query(AccountDeletion).count() == 0
    db.close()


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
