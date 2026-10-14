"""Firebase cleanup boundary without credentials, emulator or network."""
from types import SimpleNamespace
from uuid import uuid4
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from src.config import settings
from src.models import AccountDeletion
from src.services import account_deletion


def test_sdk_cleanup_targets_only_configured_project_and_missing_user_is_idempotent(monkeypatch):
    import firebase_admin
    from firebase_admin import auth
    monkeypatch.setattr(settings, "FIREBASE_AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", "synthetic-project")
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    app = SimpleNamespace(project_id="synthetic-project")
    monkeypatch.setattr(firebase_admin, "get_app", lambda name: app)
    calls = []
    def missing(uid, *, app):
        calls.append((uid, app.project_id))
        raise auth.UserNotFoundError("Synthetic missing user")
    monkeypatch.setattr(auth, "delete_user", missing)
    account_deletion.delete_firebase_identity("synthetic-project", "synthetic-uid")
    assert calls == [("synthetic-uid", "synthetic-project")]
    with pytest.raises(RuntimeError):
        account_deletion.delete_firebase_identity("different-project", "synthetic-uid")
    assert len(calls) == 1
    monkeypatch.setattr(settings, "FIREBASE_AUTH_ENABLED", False)
    with pytest.raises(RuntimeError):
        account_deletion.delete_firebase_identity("synthetic-project", "synthetic-uid")
    assert len(calls) == 1


def test_reconciler_preview_does_not_call_sdk_and_failed_apply_retains_intent(db_context, monkeypatch):
    db = db_context["session_factory"]()
    receipt = AccountDeletion(id=str(uuid4()), deleted_user_id=999,
        firebase_project_id="synthetic-project", firebase_uid="synthetic-uid", requested_at=datetime.now(timezone.utc))
    db.add(receipt)
    db.commit()
    calls = []
    def denied(*_args):
        calls.append(True)
        raise PermissionError("Synthetic IAM denial")
    monkeypatch.setattr(account_deletion, "delete_firebase_identity", denied)
    assert account_deletion.retry_identity_cleanup(db)["pending"] == 1
    assert calls == []
    assert account_deletion.retry_identity_cleanup(db, apply=True)["pending"] == 1
    db.expire_all()
    receipt = db.query(AccountDeletion).one()
    assert receipt.firebase_uid == "synthetic-uid" and receipt.completed_at is None
    assert receipt.attempts == 1 and len(calls) == 1
    db.close()


def test_legacy_processing_check_fails_safe_when_redis_is_unavailable(monkeypatch):
    def unavailable():
        raise ConnectionError("Synthetic Redis outage")
    monkeypatch.setattr(account_deletion, "get_transcription_queue", unavailable)
    with pytest.raises(HTTPException) as error:
        account_deletion.ensure_no_legacy_minutes_jobs([1])
    assert error.value.status_code == 503
    assert "outage" not in error.value.detail
