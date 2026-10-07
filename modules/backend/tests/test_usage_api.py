from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.database import get_db
from src.models import UsageEvent, User
from src.routers.usage import router
from src.security import create_access_token


@pytest.fixture
def usage_client(db_context):
    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        db = db_context["session_factory"]()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client


def _headers(user_id=1, *, admin=False):
    token = create_access_token({
        "sub": str(user_id), "username": "alice" if user_id == 1 else "bob",
        "roles": ["admin"] if admin else ["user"], "scopes": [],
    })
    return {"Authorization": f"Bearer {token}"}


def _event(db, *, user_id, guest_session_id=None, occurred_at=None, provider="gemini",
           credential_source="platform", resource_type="meeting", operation="intelligence",
           metric="input_uncached_tokens", unit="token", quantity="10", currency="USD",
           estimated_cost="0.01", cost_scope="usagi", **changes):
    row = UsageEvent(
        id=str(uuid4()), operation_id=f"op-{uuid4()}", user_id=user_id,
        guest_session_id=guest_session_id, resource_type=resource_type,
        resource_id=f"resource-{uuid4()}", operation=operation, provider=provider,
        credential_source=credential_source, metric=metric, unit=unit,
        quantity=Decimal(quantity) if quantity is not None else None,
        status="completed", occurred_at=occurred_at or datetime.now(timezone.utc),
        measurement_source="provider_response", model="safe-model", use_diarization=None,
        price_id=None, currency=currency,
        estimated_cost=Decimal(estimated_cost) if estimated_cost is not None else None,
        cost_scope=cost_scope, cost_reason="configured_estimate_not_invoice",
    )
    for name, value in changes.items():
        setattr(row, name, value)
    db.add(row)
    return row


def test_events_are_private_to_authenticated_user_even_with_spoofed_filters(db_context, usage_client):
    db = db_context["session_factory"]()
    now = datetime.now(timezone.utc)
    try:
        _event(db, user_id=1, occurred_at=now)
        _event(db, user_id=2, occurred_at=now, operation_id="bob-private")
        _event(db, user_id=None, guest_session_id="guest-only", occurred_at=now, operation_id="guest-private")
        db.get(User, 2).is_superuser = True
        db.commit()
    finally:
        db.close()

    response = usage_client.get("/usage/events?user_id=2&guest_session_id=guest-only", headers=_headers())
    assert response.status_code == 422  # Caller-supplied identity filters are unsupported.
    own = usage_client.get("/usage/events", headers=_headers()).json()
    assert own["total"] == 1
    assert all(item["operation_id"] != "bob-private" for item in own["events"])
    assert all(item["operation_id"] != "guest-private" for item in own["events"])

    admin = usage_client.get("/usage/events", headers=_headers(2, admin=True)).json()
    assert admin["total"] == 1
    assert admin["events"][0]["operation_id"] != own["events"][0]["operation_id"]


def test_events_filters_timezone_pagination_and_safe_serialization(db_context, usage_client):
    db = db_context["session_factory"]()
    now = datetime.now(timezone.utc)
    try:
        _event(db, user_id=1, occurred_at=now - timedelta(days=1), provider="gemini",
               credential_source="platform", resource_type="meeting")
        _event(db, user_id=1, occurred_at=now - timedelta(days=2), provider="assemblyai",
               credential_source="user", resource_type="transcription", metric="provider_audio_seconds",
               unit="second", quantity="0", currency="EUR", estimated_cost="0",
               cost_scope="customer", status="failed", secret="must-not-serialize")
        db.commit()
    finally:
        db.close()

    base = datetime.now(timezone.utc) - timedelta(days=3)
    params = {
        "after": base.isoformat(), "before": datetime.now(timezone.utc).isoformat(),
        "provider": "assemblyai", "credential_source": "user",
        "resource_type": "transcription", "limit": 1,
    }
    response = usage_client.get("/usage/events", params=params, headers=_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 1
    row = body["events"][0]
    assert row["quantity"] == "0E-9" or row["quantity"] == "0.000000000"
    assert row["estimated_cost"] in {"0E-12", "0E-9", "0.000000000000"}
    assert "secret" not in row
    assert "journal" not in str(body)
    assert "must-not-serialize" not in str(body)

    page_params = {"after": base.isoformat(), "before": datetime.now(timezone.utc).isoformat(),
                   "limit": 1, "offset": 1}
    page = usage_client.get("/usage/events", params=page_params, headers=_headers()).json()
    assert page["total"] == 2
    assert page["offset"] == 1
    assert len(page["events"]) == 1


@pytest.mark.parametrize("query", [
    "after=2026-10-01T00:00:00&before=2026-10-02T00:00:00Z",
    "after=2026-10-03T00:00:00Z&before=2026-10-02T00:00:00Z",
    "after=2025-01-01T00:00:00Z&before=2026-10-02T00:00:00Z",
    "limit=101",
    "offset=10001",
    "provider=unknown",
    "credential_source=guest",
    "resource_type=user",
])
def test_invalid_or_unbounded_usage_filters_are_rejected(usage_client, query):
    response = usage_client.get(f"/usage/events?{query}", headers=_headers())
    assert response.status_code == 422


def test_summary_groups_keep_currency_scope_and_unknown_separate(db_context, usage_client):
    db = db_context["session_factory"]()
    now = datetime.now(timezone.utc)
    try:
        _event(db, user_id=1, occurred_at=now, quantity="10", currency="USD",
               estimated_cost="0.25", cost_scope="usagi")
        _event(db, user_id=1, occurred_at=now, quantity=None, currency="USD",
               estimated_cost=None, cost_scope="usagi", operation_id="unknown-quantity")
        _event(db, user_id=1, occurred_at=now, quantity="5", currency="EUR",
               estimated_cost="0.50", cost_scope="customer", credential_source="user",
               operation_id="separate-currency")
        _event(db, user_id=2, occurred_at=now, quantity="999", currency="USD",
               estimated_cost="999", cost_scope="usagi", operation_id="other-owner")
        db.commit()
    finally:
        db.close()

    groups = usage_client.get("/usage/summary", headers=_headers()).json()["groups"]
    assert len(groups) == 2
    usd = next(group for group in groups if group["currency"] == "USD")
    eur = next(group for group in groups if group["currency"] == "EUR")
    assert usd["event_count"] == 2
    assert usd["known_quantity_count"] == 1
    assert usd["unknown_quantity_count"] == 1
    assert usd["quantity_total"] == "10.000000000"
    assert usd["known_cost_count"] == 1
    assert usd["unknown_cost_count"] == 1
    assert usd["estimated_cost_total"] == "0.250000000000"
    assert eur["credential_source"] == "user"
    assert eur["cost_scope"] == "customer"
    assert eur["estimated_cost_total"] == "0.500000000000"


def test_unauthenticated_and_guest_principal_cannot_read_usage(usage_client):
    assert usage_client.get("/usage/events").status_code == 401
    guest = create_access_token({"sub": "guest-session", "purpose": "guest"})
    assert usage_client.get("/usage/events", headers={"Authorization": f"Bearer {guest}"}).status_code == 401
    assert usage_client.get("/usage/summary", headers=_headers()).status_code == 200
