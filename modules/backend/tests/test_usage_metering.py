from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from src.models import GuestSession, UsageEvent, UsagePrice, User
from src.services import usage_metering


AT = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)


def _price(db, *, provider, model, metric, unit, currency, amount, quantity=1,
           version="v1", effective_from=AT, effective_until=None):
    row = UsagePrice(
        id=str(uuid4()), catalog_version=version, provider=provider, model=model,
        metric=metric, unit=unit, currency=currency,
        unit_price=Decimal(amount), unit_quantity=Decimal(quantity),
        effective_from=effective_from, effective_until=effective_until,
        source="test catalog",
    )
    db.add(row)
    db.commit()
    return row


def _record(session_factory, **changes):
    values = dict(
        operation_id=f"operation-{uuid4()}", resource_type="transcription",
        resource_id="resource-1", operation="transcription", provider="local",
        credential_source="platform", metric="processing_seconds", unit="second",
        quantity=2, status="completed", model="model-a", occurred_at=AT,
        session_factory=session_factory,
    )
    values.update(changes)
    return usage_metering.record_event(**values)


def test_event_delivery_is_idempotent_and_distinguishes_zero_from_unknown(
    db_context, monkeypatch, tmp_path
):
    monkeypatch.setattr(usage_metering.settings, "USAGE_SPOOL_DIRECTORY", str(tmp_path / "journal"))
    factory = db_context["session_factory"]
    db = factory()
    try:
        _price(db, provider="local", model="model-a", metric="processing_seconds",
               unit="second", currency="USD", amount="0.25")
    finally:
        db.close()

    event_id = _record(factory, operation_id="zero-quantity", quantity=0)
    assert _record(factory, operation_id="zero-quantity", quantity=0) == event_id
    unknown_id = _record(factory, operation_id="unknown-quantity", quantity=None)

    db = factory()
    try:
        zero = db.get(UsageEvent, event_id)
        unknown = db.get(UsageEvent, unknown_id)
        assert db.query(UsageEvent).count() == 2
        assert zero.quantity == Decimal("0E-9")
        assert zero.estimated_cost == Decimal("0E-12")
        assert unknown.quantity is None
        assert unknown.estimated_cost is None
        assert unknown.cost_reason == "quantity_unknown"
    finally:
        db.close()
    assert list((tmp_path / "journal").glob("*.json")) == []


def test_database_outage_spools_and_replay_is_dry_run_first_and_idempotent(
    db_context, monkeypatch, tmp_path
):
    monkeypatch.setattr(usage_metering.settings, "USAGE_SPOOL_DIRECTORY", str(tmp_path / "journal"))

    def unavailable_factory():
        raise OSError("database unavailable")

    assert _record(unavailable_factory, operation_id="outage-replay") is None
    journal = list((tmp_path / "journal").glob("*.json"))
    assert len(journal) == 1
    preview = usage_metering.reconcile_usage(session_factory=db_context["session_factory"])
    assert preview == {"pending": 1, "delivered": 0, "failed": 0}
    assert journal[0].exists()

    applied = usage_metering.reconcile_usage(apply=True, session_factory=db_context["session_factory"])
    assert applied == {"pending": 1, "delivered": 1, "failed": 0}
    assert not journal[0].exists()
    assert usage_metering.reconcile_usage(apply=True, session_factory=db_context["session_factory"]) == {
        "pending": 0, "delivered": 0, "failed": 0
    }
    db = db_context["session_factory"]()
    try:
        assert db.query(UsageEvent).filter_by(operation_id="outage-replay").count() == 1
    finally:
        db.close()


def test_frozen_prices_keep_version_history_currency_and_cost_scope(
    db_context, monkeypatch, tmp_path
):
    monkeypatch.setattr(usage_metering.settings, "USAGE_SPOOL_DIRECTORY", str(tmp_path / "journal"))
    factory = db_context["session_factory"]
    db = factory()
    try:
        old = _price(db, provider="assemblyai", model="universal-2", metric="provider_audio_seconds",
                     unit="second", currency="EUR", amount="1.20", quantity=60,
                     effective_from=AT - timedelta(days=1), effective_until=AT + timedelta(days=1))
        old_price_id = old.id
        _price(db, provider="assemblyai", model="universal-2", metric="provider_audio_seconds",
               unit="second", currency="GBP", amount="3.00", quantity=60, version="v2",
               effective_from=AT + timedelta(days=1))
        _price(db, provider="gemini", model="gemini-test", metric="input_uncached_tokens",
               unit="token", currency="USD", amount="0.50", quantity=1000)
    finally:
        db.close()

    aai_id = _record(factory, operation_id="byok-priced", provider="assemblyai",
                     credential_source="user", metric="provider_audio_seconds", unit="second",
                     quantity=30, model="universal-2")
    # A later catalog version cannot change an already recorded estimate.
    db = factory()
    try:
        _price(db, provider="assemblyai", model="universal-2", metric="provider_audio_seconds",
               unit="second", currency="JPY", amount="100", quantity=1, version="v3",
               effective_from=AT + timedelta(days=2))
    finally:
        db.close()
    assert _record(factory, operation_id="byok-priced", provider="assemblyai",
                   credential_source="user", metric="provider_audio_seconds", unit="second",
                   quantity=30, model="universal-2") == aai_id

    platform_id = _record(factory, operation_id="platform-priced", provider="gemini",
                          credential_source="platform", metric="input_uncached_tokens", unit="token",
                          quantity=250, model="gemini-test")
    db = factory()
    try:
        byok = db.get(UsageEvent, aai_id)
        platform = db.get(UsageEvent, platform_id)
        assert byok.price_id == old_price_id
        assert byok.currency == "EUR"
        assert byok.estimated_cost == Decimal("0.600000000000")
        assert byok.cost_scope == "customer"
        assert platform.currency == "USD"
        assert platform.estimated_cost == Decimal("0.125000000000")
        assert platform.cost_scope == "usagi"
        assert db.query(UsagePrice).count() == 4
    finally:
        db.close()


def test_late_guest_replay_uses_claimed_owner_and_deleted_users_are_anonymized(
    db_context, monkeypatch, tmp_path
):
    monkeypatch.setattr(usage_metering.settings, "USAGE_SPOOL_DIRECTORY", str(tmp_path / "journal"))
    factory = db_context["session_factory"]
    guest_id = "guest-session-1"
    db = factory()
    guest = GuestSession(id=guest_id, expires_at=AT + timedelta(days=1))
    db.add(guest)
    db.commit()
    db.close()

    def unavailable_factory():
        raise OSError("database unavailable")

    assert _record(unavailable_factory, operation_id="late-guest", guest_session_id=guest_id) is None
    assert _record(unavailable_factory, operation_id="deleted-owner", user_id=2) is None

    db = factory()
    try:
        db.get(GuestSession, guest_id).claimed_by_user_id = 1
        db.delete(db.get(User, 2))
        db.commit()
    finally:
        db.close()

    result = usage_metering.reconcile_usage(apply=True, session_factory=factory)
    assert result == {"pending": 2, "delivered": 2, "failed": 0}
    db = factory()
    try:
        guest_event = db.query(UsageEvent).filter_by(operation_id="late-guest").one()
        deleted_event = db.query(UsageEvent).filter_by(operation_id="deleted-owner").one()
        assert guest_event.guest_session_id == guest_id
        assert guest_event.user_id == 1
        assert deleted_event.user_id is None
    finally:
        db.close()


def test_gemini_callback_counts_cached_tokens_once_and_failed_provider_cost_stays_unknown(
    db_context, monkeypatch, tmp_path
):
    monkeypatch.setattr(usage_metering.settings, "USAGE_SPOOL_DIRECTORY", str(tmp_path / "journal"))
    factory = db_context["session_factory"]
    db = factory()
    try:
        _price(db, provider="gemini", model="gemini-test", metric="input_uncached_tokens",
               unit="token", currency="USD", amount="1", quantity=100)
        _price(db, provider="assemblyai", model="universal-2", metric="provider_audio_seconds",
               unit="second", currency="USD", amount="1", quantity=1)
    finally:
        db.close()

    recorder = usage_metering.UsageRecorder(
        operation_id="gemini-callback", resource_type="meeting", resource_id="meeting-1",
        operation="intelligence", provider="gemini", credential_source="user", model="gemini-test",
        user_id=1, session_factory=factory, occurred_at=AT,
    )

    class Usage:
        prompt_token_count = 100
        candidates_token_count = 10
        total_token_count = 110
        thoughts_token_count = 3
        cached_content_token_count = 20
        tool_use_prompt_token_count = 4

    class Response:
        usage_metadata = Usage()

    from src.services.meeting_minutes import MeetingMinutesGenerator
    generator = MeetingMinutesGenerator.__new__(MeetingMinutesGenerator)
    generator._usage_observer = recorder.provider_response
    generator._observe_usage(Response(), started=0, status="response")

    aai = usage_metering.UsageRecorder(
        operation_id="aai-failed", resource_type="transcription", resource_id="job-1",
        operation="transcription", provider="assemblyai", credential_source="platform",
        model="universal-2", session_factory=factory, occurred_at=AT,
    )
    aai.provider_response({"phase": "polled", "status": "error", "audio_duration_seconds": 12})

    db = factory()
    try:
        rows = db.query(UsageEvent).all()
        by_metric = {row.metric: row for row in rows if row.operation_id == "gemini-callback"}
        assert by_metric["input_tokens"].quantity == Decimal("100.000000000")
        assert by_metric["cache_read_tokens"].quantity == Decimal("20.000000000")
        assert by_metric["input_uncached_tokens"].quantity == Decimal("80.000000000")
        assert by_metric["input_uncached_tokens"].estimated_cost == Decimal("0.800000000000")
        assert by_metric["input_tokens"].estimated_cost is None
        failed_audio = next(row for row in rows if row.operation_id == "aai-failed" and row.metric == "provider_audio_seconds")
        assert failed_audio.quantity == Decimal("12.000000000")
        assert failed_audio.status == "failed"
        assert failed_audio.estimated_cost is None
        assert failed_audio.cost_reason == "provider_billing_unknown"
    finally:
        db.close()


def test_usage_events_and_journal_do_not_capture_content_or_credentials(
    db_context, monkeypatch, tmp_path
):
    monkeypatch.setattr(usage_metering.settings, "USAGE_SPOOL_DIRECTORY", str(tmp_path / "journal"))
    event_id = _record(db_context["session_factory"], operation_id="safe-operation")

    expected = set(UsageEvent.__table__.columns.keys()) - {"recorded_at"}
    journal = next((tmp_path / "journal").glob("*.json"), None)
    assert journal is None  # A successfully delivered event removes its journal entry.
    db = db_context["session_factory"]()
    try:
        event = db.get(UsageEvent, event_id)
        assert set(UsageEvent.__table__.columns.keys()) >= expected
        assert not {"transcript", "filename", "audio_path", "api_key", "token", "secret"} & set(expected)
        assert "private transcript" not in str(event.__dict__)
        assert "synthetic-api-key" not in str(event.__dict__)
    finally:
        db.close()


def test_older_gemini_sdk_unclassified_tokens_are_not_guessed_or_priced(db_context):
    recorder = usage_metering.UsageRecorder(
        operation_id="old-sdk-categories", resource_type="meeting", resource_id="7", operation="intelligence",
        provider="gemini", credential_source="user", model="gemini-test", user_id=1,
        session_factory=db_context["session_factory"])
    recorder.provider_response(dict(status="response", prompt_tokens=100, candidates_tokens=10,
                                    total_tokens=150, cached_tokens=0))
    with db_context["session_factory"]() as db:
        rows = {r.metric: r for r in db.query(UsageEvent).all()}
        assert rows["unclassified_tokens"].quantity == Decimal(40)
        assert rows["unclassified_tokens"].estimated_cost is None
        assert rows["thinking_tokens"].quantity is None
        assert rows["tool_tokens"].quantity is None
        assert rows["input_uncached_tokens"].quantity == Decimal(100)


def test_journal_disk_failure_falls_back_to_database_without_breaking_result(db_context, monkeypatch):
    monkeypatch.setattr(usage_metering, "_journal", lambda _data: (_ for _ in ()).throw(OSError("synthetic disk fault")))
    identifier = _record(db_context["session_factory"], operation_id="disk-fault")
    assert identifier
    with db_context["session_factory"]() as db:
        assert db.get(UsageEvent, identifier).quantity == Decimal(2)


def test_identifier_cannot_be_reused_for_different_resource(db_context):
    identifier = _record(db_context["session_factory"], operation_id="conflicting-identity", resource_id="7")
    assert identifier
    assert _record(db_context["session_factory"], operation_id="conflicting-identity", resource_id="8") is None
    with db_context["session_factory"]() as db:
        assert db.query(UsageEvent).one().resource_id == "7"
