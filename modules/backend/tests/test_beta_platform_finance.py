from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from src.models import PlatformProviderBudget, PlatformProviderCall, Transcription
from src.services import platform_budget as finance
from src.config import settings


def configured(monkeypatch):
    for key, value in {
        "AAI_PLATFORM_ENABLED": True, "AAI_PLATFORM_BUDGET_CENTS": 1500,
        "AAI_PLATFORM_ALERT_CENTS": 1200, "AAI_PLATFORM_HOURLY_USD": Decimal("0.23"),
        "AAI_PLATFORM_PRICE_VERSION": "public-2026-10-15",
        "AAI_PLATFORM_KEY_REFERENCE": "beta-primary", "AAI_PLATFORM_PROJECT_REFERENCE": "beta",
        "AAI_BETA_ROUND_ID": "round-one",
    }.items():
        monkeypatch.setattr(settings, key, value)


def checked(db, monkeypatch, amount="50"):
    configured(monkeypatch)
    finance.record_balance_check(db, available_usd=Decimal(amount), checked_at=finance.now_utc(),
        key_reference="beta-primary", project_reference="beta", exclusive=True, actor_user_id=1)
    db.commit()


def transcription(db):
    row = Transcription(filename="synthetic.wav", original_filename="synthetic.wav",
        file_size_mb=0.1, duration_seconds=0, transcription_model="assemblyai", status="queued")
    db.add(row)
    db.flush()
    return row


def test_verified_duration_reservation_is_proportional_and_subcent(db_context, monkeypatch):
    with db_context["session_factory"]() as db:
        checked(db, monkeypatch)
        row = transcription(db)
        finance.reserve_platform_call(db, row.id, "local")
        finance.begin_platform_call(db, row.id, duration_seconds=60)
        call = db.query(PlatformProviderCall).one()
        assert call.reserved_cents == Decimal("0.38333334")
        assert call.model == "universal-3-5-pro"
        assert call.state == "attempted"
        assert db.get(PlatformProviderBudget, "assemblyai").reserved_cents == call.reserved_cents


def test_reduced_budget_rejects_already_queued_call_before_attempt(db_context, monkeypatch):
    with db_context["session_factory"]() as db:
        checked(db, monkeypatch)
        row = transcription(db)
        finance.reserve_platform_call(db, row.id, "local")
        db.commit()
        monkeypatch.setattr(settings, "AAI_PLATFORM_BUDGET_CENTS", 1)
        with pytest.raises(HTTPException):
            finance.begin_platform_call(db, row.id, duration_seconds=600)
        assert db.query(PlatformProviderCall).one().state == "reserved"


def test_manual_balance_is_required_and_can_expire(db_context, monkeypatch):
    with db_context["session_factory"]() as db:
        configured(monkeypatch)
        row = transcription(db)
        with pytest.raises(HTTPException):
            finance.reserve_platform_call(db, row.id, "local")
        db.rollback()
        checked(db, monkeypatch)
        budget = db.get(PlatformProviderBudget, "assemblyai")
        budget.balance_checked_at = finance.now_utc() - timedelta(hours=25)
        db.commit()
        with pytest.raises(HTTPException):
            finance.reserve_platform_call(db, transcription(db).id, "local")


def test_remote_id_survives_timeout_and_error_release_is_idempotent(db_context, monkeypatch):
    with db_context["session_factory"]() as db:
        checked(db, monkeypatch)
        row = transcription(db)
        finance.reserve_platform_call(db, row.id, "local")
        finance.begin_platform_call(db, row.id, duration_seconds=60)
        finance.observe_platform_call(db, row.id, {"provider_id": "synthetic-remote", "status": "queued"})
        db.commit()
        finance.observe_platform_call(db, row.id, {"provider_id": "synthetic-remote", "status": "unknown"})
        db.commit()
        call = db.query(PlatformProviderCall).one()
        assert call.remote_transcript_id == "synthetic-remote"
        assert call.settled_at is None
        assert db.get(PlatformProviderBudget, "assemblyai").reserved_cents > 0
        with pytest.raises(HTTPException):
            finance.begin_platform_call(db, row.id, duration_seconds=60)
        event = {"provider_id": "synthetic-remote", "status": "error"}
        finance.observe_platform_call(db, row.id, event)
        db.commit()
        finance.observe_platform_call(db, row.id, event)
        db.commit()
        assert db.get(PlatformProviderBudget, "assemblyai").reserved_cents == 0


def test_unknown_attempt_holds_global_slot_and_exclusivity_can_be_withdrawn(db_context, monkeypatch):
    with db_context["session_factory"]() as db:
        checked(db, monkeypatch)
        first, second = transcription(db), transcription(db)
        finance.reserve_platform_call(db, first.id, "local")
        finance.reserve_platform_call(db, second.id, "local")
        finance.begin_platform_call(db, first.id, duration_seconds=60)
        with pytest.raises(HTTPException) as denied:
            finance.begin_platform_call(db, second.id, duration_seconds=60)
        assert denied.value.status_code == 429
        finance.record_balance_check(db, available_usd=Decimal(50), checked_at=finance.now_utc(),
            key_reference="beta-primary", project_reference="beta", exclusive=False, actor_user_id=1)
        db.commit()
        assert finance.platform_budget_has_headroom(db) is False


def test_alert_is_durable_and_not_a_public_budget_response(db_context, auth_headers, monkeypatch):
    from src.models import AuditEvent, User
    with db_context["session_factory"]() as db:
        checked(db, monkeypatch)
        budget = db.get(PlatformProviderBudget, "assemblyai")
        budget.alert_cents = Decimal("0.1")
        db.commit()
        row = transcription(db)
        finance.reserve_platform_call(db, row.id, "local")
        finance.begin_platform_call(db, row.id, duration_seconds=60)
        assert budget.alerted_at is not None
        assert db.query(AuditEvent).filter_by(event="provider.budget_alert").count() == 1
        assert db_context["client"].get("/admin/providers/assemblyai/operations", headers=auth_headers()).status_code == 403
        db.get(User, 1).is_superuser = True
        db.commit()
        response = db_context["client"].get("/admin/providers/assemblyai/operations", headers=auth_headers())
        assert response.status_code == 200
        assert response.json()["authorized_usd"] == "0.0038333334"
        own = db_context["client"].get("/account/plan", headers=auth_headers()).json()
        assert "external_balance_snapshot_usd" not in own
        assert "hard_stop_usd" not in own


def test_external_snapshot_lower_than_internal_budget_blocks_before_call(db_context, monkeypatch):
    with db_context["session_factory"]() as db:
        checked(db, monkeypatch, amount="0.001")
        with pytest.raises(HTTPException) as denied:
            finance.reserve_platform_call(db, transcription(db).id, "local")
        assert denied.value.status_code == 429
        assert db.query(PlatformProviderCall).count() == 0


def test_recorded_balance_and_budget_changes_require_admin(db_context, auth_headers, monkeypatch):
    from src.models import AuditEvent, User
    configured(monkeypatch)
    payload = {"available_usd": "50", "checked_at": finance.now_utc().isoformat(),
        "key_reference": "beta-primary", "project_reference": "beta", "exclusive": True}
    client = db_context["client"]
    assert client.post("/admin/providers/assemblyai/balance-check", headers=auth_headers(), json=payload).status_code == 403
    with db_context["session_factory"]() as db:
        db.get(User, 1).is_superuser = True
        db.commit()
    assert client.post("/admin/providers/assemblyai/balance-check", headers=auth_headers(), json=payload).status_code == 200
    change = {"hard_stop_usd": "16", "alert_usd": "12", "reason": "manual_review"}
    assert client.patch("/admin/providers/assemblyai/budget", headers=auth_headers(), json=change).status_code == 200
    with db_context["session_factory"]() as db:
        assert db.query(AuditEvent).filter_by(event="provider.balance_checked").count() == 1
        assert db.query(AuditEvent).filter_by(event="provider.budget_changed").count() == 1
        assert db.get(PlatformProviderBudget, "assemblyai").limit_cents == 1600
    # Raising an environment setting alone does not update the persisted ceiling.
    monkeypatch.setattr(settings, "AAI_PLATFORM_BUDGET_CENTS", 2000)
    with db_context["session_factory"]() as db:
        assert finance._ceiling(db.get(PlatformProviderBudget, "assemblyai")) == 1600


@pytest.mark.parametrize("attempted", [False, True])
def test_manual_reconciliation_releases_only_inactive_proven_unsubmitted_calls(
    db_context, auth_headers, monkeypatch, attempted
):
    from types import SimpleNamespace
    from rq.exceptions import NoSuchJobError
    from rq.job import Job
    from src.models import AuditEvent, User
    from src.workers import config

    with db_context["session_factory"]() as db:
        checked(db, monkeypatch)
        db.get(User, 1).is_superuser = True
        row = transcription(db)
        finance.reserve_platform_call(db, row.id, "local")
        if attempted:
            finance.begin_platform_call(db, row.id, duration_seconds=60)
        call_id = db.query(PlatformProviderCall).one().id
        # Deletion must not erase the immutable queue reference or release money.
        db.delete(row)
        db.commit()

    monkeypatch.setattr(config, "get_transcription_queue", lambda: db_context["queue"])
    monkeypatch.setattr(Job, "fetch", lambda *args, **kwargs: SimpleNamespace(get_status=lambda **kw: "started"))
    client = db_context["client"]
    path = f"/admin/providers/assemblyai/calls/{call_id}/reconcile"
    payload = {"decision": "not_submitted", "reason": "dashboard_verified"}
    assert client.post(path, headers=auth_headers(), json=payload).status_code == 409

    def missing(*args, **kwargs):
        raise NoSuchJobError("synthetic queue has no job")

    monkeypatch.setattr(Job, "fetch", missing)
    assert client.post(path, headers=auth_headers(), json=payload).status_code == 200
    assert client.post(path, headers=auth_headers(), json=payload).status_code == 200
    with db_context["session_factory"]() as db:
        assert db.get(PlatformProviderBudget, "assemblyai").reserved_cents == 0
        assert db.get(PlatformProviderCall, call_id).provider_status == "not_submitted"
        assert db.query(AuditEvent).filter_by(event="provider.call_reconciled").count() == 1


def test_manual_balance_recheck_never_resets_accumulated_authorization(db_context, monkeypatch):
    with db_context["session_factory"]() as db:
        checked(db, monkeypatch)
        row = transcription(db)
        finance.reserve_platform_call(db, row.id, "local")
        finance.begin_platform_call(db, row.id, duration_seconds=60)
        with pytest.raises(HTTPException) as denied:
            finance.record_balance_check(db, available_usd=Decimal("49"), checked_at=finance.now_utc(),
                key_reference="beta-primary", project_reference="beta", exclusive=True, actor_user_id=1)
        assert denied.value.status_code == 409
        finance.observe_platform_call(db, row.id, {"provider_id": "synthetic-completed", "status": "completed",
                                                 "audio_duration_seconds": 60})
        db.commit()
        finance.record_balance_check(db, available_usd=Decimal("49"), checked_at=finance.now_utc(),
            key_reference="beta-primary", project_reference="beta", exclusive=True, actor_user_id=1)
        db.commit()
        budget = db.get(PlatformProviderBudget, "assemblyai")
        assert budget.reserved_cents == budget.balance_baseline_cents == Decimal("0.38333334")


def test_legacy_budget_requires_explicit_quiescent_check_and_preserves_amount(db_context, monkeypatch):
    configured(monkeypatch)
    with db_context["session_factory"]() as db:
        db.add(PlatformProviderBudget(provider="assemblyai", limit_cents=200, reserved_cents=17))
        row = transcription(db)
        db.add(PlatformProviderCall(transcription_id=row.id, provider="assemblyai", context="local",
                                   credential_source="platform", reserved_cents=17, state="attempted"))
        db.commit()
        with pytest.raises(HTTPException):
            finance.record_balance_check(db, available_usd=Decimal(40), checked_at=finance.now_utc(),
                key_reference="beta-primary", project_reference="beta", exclusive=True, actor_user_id=1)
        # Old calls retain their conservative authorization; no retroactive price.
        finance.observe_platform_call(db, row.id, {"provider_id": "synthetic-historical",
            "status": "completed", "audio_duration_seconds": 60})
        db.commit()
        assert db.query(PlatformProviderCall).one().estimated_cost_cents is None
        finance.record_balance_check(db, available_usd=Decimal(40), checked_at=finance.now_utc(),
            key_reference="beta-primary", project_reference="beta", exclusive=True, actor_user_id=1)
        db.commit()
        budget = db.get(PlatformProviderBudget, "assemblyai")
        assert budget.round_id == "round-one"
        assert budget.reserved_cents == budget.balance_baseline_cents == 17
        assert budget.limit_cents == 200


def test_round_invitation_slots_do_not_reset_after_revocation_expiry_or_account_erasure(db_context, monkeypatch):
    from uuid import uuid4
    from src.models import BetaAccessGrant, User
    with db_context["session_factory"]() as db:
        checked(db, monkeypatch)
        db.add_all([User(id=i, username=f"synthetic-{i}", email=f"{i}@example.invalid",
                         hashed_password="unused") for i in range(3, 7)])
        db.flush()
        for user_id in range(1, 6):
            finance.lock_beta_enrollment(db, "round-one", user_id)
            db.add(BetaAccessGrant(id=str(uuid4()), user_id=user_id, round_id="round-one",
                capabilities=["transcription.platform"], expires_at=finance.now_utc() - timedelta(hours=1)))
            db.flush()
        db.query(BetaAccessGrant).filter_by(user_id=1).update({"revoked_at": finance.now_utc()})
        db.delete(db.get(User, 5))
        db.commit()
        assert db.get(PlatformProviderBudget, "assemblyai").invited_count == 5
        # The same surviving participant can receive a new grant, not a new slot.
        finance.lock_beta_enrollment(db, "round-one", 1)
        with pytest.raises(HTTPException) as denied:
            finance.lock_beta_enrollment(db, "round-one", 6)
        assert denied.value.status_code == 409
        assert db.get(PlatformProviderBudget, "assemblyai").invited_count == 5
