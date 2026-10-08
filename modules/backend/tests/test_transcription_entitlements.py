"""Observable plan rules; positive legacy fixtures do not grant these accounts beta."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from src.config import settings
from src.models import BetaAccessGrant, Transcription, TranscriptionJob, TranscriptionOwnership, User
from src.services import transcription_entitlements as policy


@pytest.fixture
def account(db_context, monkeypatch):
    db = db_context["session_factory"]()
    db.query(BetaAccessGrant).delete()
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_ENABLED", False)
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_HOMOLOGATED", False)
    db.commit()
    yield db
    db.close()


def job(db, user_id=1, provider="whisper", source="none", status="queued"):
    row = Transcription(filename="opaque.wav", original_filename="Teste.wav", file_size_mb=0,
        duration_seconds=0, transcription_model=provider, segments=[], status=status)
    db.add(row)
    db.flush()
    db.add(TranscriptionOwnership(transcription_id=row.id, user_id=user_id, owner_sub="legacy-test"))
    db.add(TranscriptionJob(transcription_id=row.id, input_path="opaque.wav",
        transcription_model=provider, credential_source=source, status=status))
    db.flush()
    return row


def reserve(db, row, *, user_id=1, provider="whisper", source="none", now=None, size=10):
    return policy.reserve_transcription(db, user_id, row.id,
        {"provider": provider, "credential_source": source}, size, f"object:test-{row.id}", now=now)


def limits(monkeypatch, **changes):
    values = {"monthly_usagi_seconds": 60, "max_audio_seconds": 60,
        "max_stored_bytes": 100, "max_queued_jobs": 3, "max_processing_jobs": 1}
    values.update(changes)
    monkeypatch.setattr(settings, "PLAN_POLICIES_JSON", json.dumps({k: values for k in ("free", "starter", "business", "beta")}))


def local_ready(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_ENABLED", True)
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_HOMOLOGATED", True)


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("provider,source", [("whisper", "none"), ("assemblyai", "user"),
    ("assemblyai", "platform"), ("gemini", "user"), ("gemini", "platform")])
def test_all_free_accounts_including_admin_are_denied(account, admin, provider, source):
    account.get(User, 1).is_superuser = admin
    account.commit()
    with pytest.raises(HTTPException) as error:
        policy.require_execution(account, 1, provider, source)
    assert error.value.status_code == 403


def test_starter_byok_is_separate_and_does_not_inherit_platform(account, monkeypatch):
    account.get(User, 1).plan = "starter"
    account.commit()
    limits(monkeypatch, monthly_usagi_seconds=0)
    row = job(account, provider="assemblyai", source="user")
    hold = reserve(account, row, provider="assemblyai", source="user")
    account.commit()
    policy.claim_reservation(account, row.id)
    account.commit()
    policy.authorize_inference(account, row.id, 12.25)
    account.commit()
    policy.finish_reservation(account, row.id, success=True)
    account.commit()
    view = policy.plan_view(account, 1)
    assert hold.source == "byok"
    assert Decimal(view["byok"]["measured_seconds"]) == Decimal("12.250")
    assert Decimal(view["quota"]["consumed_seconds"]) == 0
    with pytest.raises(HTTPException):
        policy.require_execution(account, 1, "assemblyai", "platform")


@pytest.mark.parametrize("enabled,homologated", [(False, False), (True, False), (False, True)])
def test_beta_cannot_enable_unhomologated_local(account, monkeypatch, enabled, homologated):
    from .entitlement_helpers import grant_test_beta
    grant_test_beta(account, 1)
    account.commit()
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_ENABLED", enabled)
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_HOMOLOGATED", homologated)
    with pytest.raises(HTTPException):
        policy.require_execution(account, 1, "whisper", "none")


def test_verified_duration_consumed_once_and_deletion_never_refunds(account, monkeypatch):
    limits(monkeypatch)
    local_ready(monkeypatch)
    row = job(account)
    hold = reserve(account, row)
    account.commit()
    assert reserve(account, row).id == hold.id
    policy.claim_reservation(account, row.id)
    account.commit()
    policy.authorize_inference(account, row.id, 10.0001)
    account.commit()
    assert hold.measured_seconds == Decimal("10.001")
    policy.finish_reservation(account, row.id, success=True)
    account.commit()
    policy.finish_reservation(account, row.id, success=True)
    account.delete(row)
    account.commit()
    assert Decimal(policy.plan_view(account, 1)["quota"]["consumed_seconds"]) == Decimal("10.001")
    account.refresh(hold)
    assert hold.transcription_id is None
    with pytest.raises(HTTPException):
        policy.claim_reservation(account, row.id)


@pytest.mark.parametrize("duration", [61, 0, -1, float("nan"), float("inf")])
def test_duration_is_checked_before_irreversible_start(account, monkeypatch, duration):
    limits(monkeypatch)
    local_ready(monkeypatch)
    row = job(account)
    hold = reserve(account, row)
    account.commit()
    policy.claim_reservation(account, row.id)
    account.commit()
    with pytest.raises(HTTPException):
        policy.authorize_inference(account, row.id, duration)
    assert hold.state == "processing"
    policy.finish_reservation(account, row.id)
    account.commit()
    assert hold.state == "released"
    assert Decimal(policy.plan_view(account, 1)["quota"]["available_seconds"]) == 60


def test_started_failure_retains_unknown_hold_and_cannot_retry(account, monkeypatch):
    limits(monkeypatch)
    local_ready(monkeypatch)
    row = job(account)
    hold = reserve(account, row)
    account.commit()
    policy.claim_reservation(account, row.id)
    account.commit()
    policy.authorize_inference(account, row.id, 14)
    account.commit()
    assert policy.recover_reservation(account, row.id) is False
    account.commit()
    policy.finish_reservation(account, row.id)
    account.commit()
    assert hold.state == "unknown"
    assert Decimal(policy.plan_view(account, 1)["quota"]["reserved_seconds"]) == 14


def test_safe_retry_retains_month_and_same_hold(account, monkeypatch):
    limits(monkeypatch)
    local_ready(monkeypatch)
    december = datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)
    january = december + timedelta(minutes=2)
    row = job(account)
    hold = reserve(account, row, now=december)
    account.commit()
    policy.claim_reservation(account, row.id)
    account.commit()
    assert policy.recover_reservation(account, row.id) is True
    account.commit()
    assert reserve(account, row, now=january).id == hold.id
    assert hold.period_start.isoformat() == "2026-12-01"
    assert Decimal(policy.plan_view(account, 1, now=january)["quota"]["reserved_seconds"]) == 0
    assert policy.plan_view(account, 1, now=january)["renews_at"].startswith("2027-02-01")


def test_quota_storage_queue_and_isolation(account, monkeypatch):
    limits(monkeypatch, max_audio_seconds=30, max_stored_bytes=20, max_queued_jobs=1)
    local_ready(monkeypatch)
    first = job(account)
    hold = reserve(account, first, size=20)
    account.commit()
    assert Decimal(policy.plan_view(account, 2)["quota"]["available_seconds"]) == 60
    second = job(account)
    with pytest.raises(HTTPException) as error:
        reserve(account, second)
    assert error.value.status_code == 429
    with pytest.raises(HTTPException):
        reserve(account, first, user_id=2)
    account.query(TranscriptionJob).filter_by(transcription_id=first.id).update({"status": "failed"})
    policy.finish_reservation(account, first.id)
    account.commit()
    with pytest.raises(HTTPException):
        reserve(account, second)
    policy.release_storage(account, hold.input_reference)
    account.commit()
    assert reserve(account, second).stored_bytes == 10


def test_processing_slots_and_revocation_before_inference(account, monkeypatch):
    limits(monkeypatch, max_audio_seconds=30)
    local_ready(monkeypatch)
    first, second = job(account), job(account)
    reserve(account, first)
    reserve(account, second)
    account.commit()
    policy.claim_reservation(account, first.id)
    account.query(TranscriptionJob).filter_by(transcription_id=first.id).update({"status": "processing"})
    account.commit()
    with pytest.raises(HTTPException) as error:
        policy.claim_reservation(account, second.id)
    assert error.value.status_code == 429
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_HOMOLOGATED", False)
    with pytest.raises(HTTPException):
        policy.authorize_inference(account, first.id, 5)


def test_lowered_duration_limit_is_rechecked_for_an_already_reserved_job(account, monkeypatch):
    local_ready(monkeypatch)
    limits(monkeypatch)
    row = job(account)
    hold = reserve(account, row)
    account.commit()
    policy.claim_reservation(account, row.id)
    account.commit()
    limits(monkeypatch, max_audio_seconds=5)
    with pytest.raises(HTTPException):
        policy.authorize_inference(account, row.id, 6)
    assert hold.state == "processing"


@pytest.mark.parametrize("configuration", ["{}", "invalid", '{"unexpected":{}}', '{"free":{"max_audio_seconds":true}}'])
def test_unconfigured_limits_fail_closed(account, monkeypatch, configuration):
    local_ready(monkeypatch)
    monkeypatch.setattr(settings, "PLAN_POLICIES_JSON", configuration)
    with pytest.raises(HTTPException) as error:
        reserve(account, job(account))
    assert error.value.status_code == 503


def test_sqlite_legacy_reads_do_not_authorize_non_atomic_real_processing(account, monkeypatch):
    local_ready(monkeypatch)
    limits(monkeypatch)
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    assert policy.plan_view(account, 1)["plan"] == "free"
    with pytest.raises(HTTPException) as error:
        reserve(account, job(account))
    assert error.value.status_code == 503


def test_plan_api_private_admin_grants_expire_revoke_and_audit(account, db_context, auth_headers):
    client = db_context["client"]
    headers = auth_headers()
    assert client.get("/account/plan").status_code == 401
    assert client.patch("/admin/accounts/2/plan", headers=auth_headers(roles=["admin"]),
        json={"plan": "starter", "reason": "beta_test"}).status_code == 403
    account.get(User, 1).is_superuser = True
    account.commit()
    response = client.post("/admin/accounts/2/beta", headers=headers,
        json={"capabilities": ["transcription.byok"], "expires_at": (policy.now_utc() + timedelta(hours=1)).isoformat()})
    assert response.status_code == 201
    grant_id = response.json()["id"]
    assert client.get("/account/plan", headers=auth_headers("bob")).json()["beta"]["capabilities"] == ["transcription.byok"]
    assert client.get("/account/plan?user_id=2", headers=headers).json()["beta"] is None
    assert client.delete(f"/admin/accounts/1/beta/{grant_id}", headers=headers).status_code == 404
    assert client.delete(f"/admin/accounts/2/beta/{grant_id}", headers=headers).status_code == 200
    assert client.delete(f"/admin/accounts/2/beta/{grant_id}", headers=headers).status_code == 200
    account.expire_all()
    with pytest.raises(HTTPException):
        policy.require_execution(account, 2, "assemblyai", "user")
    grant = account.get(BetaAccessGrant, grant_id)
    grant.revoked_at = None
    grant.expires_at = policy.now_utc() - timedelta(seconds=1)
    account.commit()
    with pytest.raises(HTTPException):
        policy.require_execution(account, 2, "assemblyai", "user")
    from src.models import AuditEvent
    assert account.query(AuditEvent).filter(AuditEvent.event.in_(["account.beta_granted", "account.beta_revoked"])).count() == 2


def test_admin_plan_assignment_is_explicit_and_bad_beta_input_is_rejected(account, db_context, auth_headers):
    account.get(User, 1).is_superuser = True
    account.commit()
    client, headers = db_context["client"], auth_headers()
    assert client.patch("/admin/accounts/2/plan", headers=headers,
        json={"plan": "starter", "reason": "user_request"}).status_code == 200
    assert client.get("/account/plan", headers=auth_headers("bob")).json()["plan"] == "starter"
    with pytest.raises(HTTPException):
        policy.require_execution(account, 1, "assemblyai", "user")
    policy.require_execution(account, 2, "assemblyai", "user")
    for payload in (
        {"capabilities": ["bypass_budget"], "expires_at": (policy.now_utc() + timedelta(hours=1)).isoformat()},
        {"capabilities": ["transcription.byok"], "expires_at": "2020-01-01T00:00:00Z"},
        {"capabilities": ["transcription.byok"], "expires_at": "2099-01-01T00:00:00"},
    ):
        assert client.post("/admin/accounts/2/beta", headers=headers, json=payload).status_code == 422


def test_revoked_beta_is_rechecked_before_byok_inference(account, monkeypatch):
    from .entitlement_helpers import grant_test_beta
    grant_test_beta(account, 1)
    account.commit()
    limits(monkeypatch)
    row = job(account, provider="assemblyai", source="user")
    hold = reserve(account, row, provider="assemblyai", source="user")
    account.commit()
    policy.claim_reservation(account, row.id)
    account.commit()
    account.query(BetaAccessGrant).filter_by(user_id=1).update({"revoked_at": policy.now_utc()})
    account.commit()
    with pytest.raises(HTTPException) as error:
        policy.authorize_inference(account, row.id, 10)
    assert error.value.status_code == 403
    assert hold.state == "processing"
    policy.finish_reservation(account, row.id)
    account.commit()
    assert hold.state == "released"


def test_reconciliation_requires_admin_terminal_jobs_and_available_redis(account, monkeypatch, db_context, auth_headers):
    from rq.exceptions import NoSuchJobError
    from src.routers import account_plans
    limits(monkeypatch)
    local_ready(monkeypatch)
    row = job(account)
    hold = reserve(account, row)
    account.commit()
    policy.claim_reservation(account, row.id)
    account.commit()
    policy.authorize_inference(account, row.id, 8)
    account.commit()
    policy.finish_reservation(account, row.id)
    account.commit()
    url = f"/admin/transcription-reservations/{hold.id}/reconcile"
    body = {"decision": "consumed", "reason": "processing_verified"}
    client, headers = db_context["client"], auth_headers()
    assert client.post(url, headers=headers, json=body).status_code == 403
    account.get(User, 1).is_superuser = True
    account.commit()
    assert client.post(url, headers=headers, json=body).status_code == 409
    account.query(TranscriptionJob).filter_by(transcription_id=row.id).update({"status": "failed"})
    account.commit()
    monkeypatch.setattr(account_plans, "get_transcription_queue", lambda: (_ for _ in ()).throw(ConnectionError()))
    assert client.post(url, headers=headers, json=body).status_code == 503
    monkeypatch.setattr(account_plans, "get_transcription_queue", lambda: db_context["queue"])
    class ActiveJob:
        def get_status(self):
            return "started"
    monkeypatch.setattr(account_plans.Job, "fetch", lambda *_args, **_kwargs: ActiveJob())
    assert client.post(url, headers=headers, json=body).status_code == 409
    def missing(*_args, **_kwargs):
        raise NoSuchJobError()
    monkeypatch.setattr(account_plans.Job, "fetch", missing)
    assert client.post(url, headers=headers, json=body).status_code == 200
    account.expire_all()
    assert account.get(type(hold), hold.id).state == "consumed"
    assert Decimal(policy.plan_view(account, 1)["quota"]["consumed_seconds"]) == 8
    assert client.post(url, headers=headers, json=body).status_code == 409
