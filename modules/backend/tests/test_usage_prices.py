from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.models import UsageEvent, UsagePrice
from src.services.usage_metering import record_event, reconcile_usage
from src.services.usage_prices import import_prices


def catalog(**changes):
    row = dict(catalog_version="operator-test-v1", provider="gemini", model="gemini-test",
               metric="output_tokens", unit="token", currency="USD", unit_price="0.1", unit_quantity="1000",
               effective_from="2026-01-01T00:00:00+00:00", effective_until=None,
               source="https://example.test/operator-tariff")
    row.update(changes)
    return [row]


def test_catalog_dry_run_idempotent_import_and_immutable_versions(db_context):
    db = db_context["session_factory"]()
    assert import_prices(db, catalog())["dry_run"]
    assert db.query(UsagePrice).count() == 0
    assert import_prices(db, catalog(), apply=True)["new"] == 1
    db.commit()
    assert import_prices(db, catalog(), apply=True)["new"] == 0
    with pytest.raises(ValueError, match="immutable"):
        import_prices(db, catalog(unit_price="0.2"), apply=True)
    assert db.query(UsagePrice).one().unit_price == Decimal("0.1")
    assert import_prices(db, catalog(catalog_version="operator-test-v2", unit_price="0.2",
                                      effective_from="2027-01-01T00:00:00+00:00"), apply=True)["new"] == 1
    db.commit()
    assert db.query(UsagePrice).count() == 2
    db.close()


@pytest.mark.parametrize("changes", [
    {"unit_price": 0.1}, {"unit_price": "NaN"}, {"unit_price": "-1"},
    {"unit_price": "0.0000000000001"}, {"unit_quantity": "0"},
    {"unit": "second"}, {"metric": "total_tokens"}, {"currency": "usd"},
    {"source": "https://example.test/?key=synthetic"},
    {"source": "https://synthetic:password@example.test/rates"},
    {"effective_from": "2026-01-01T00:00:00"},
    {"effective_until": "2025-01-01T00:00:00+00:00"},
])
def test_catalog_rejects_unsafe_ambiguous_units_and_precision(db_context, changes):
    with db_context["session_factory"]() as db:
        with pytest.raises(ValueError):
            import_prices(db, catalog(**changes), apply=True)
        assert db.query(UsagePrice).count() == 0


def test_outage_replay_does_not_reprice_unknown_with_later_catalog(db_context):
    def outage():
        raise OSError("synthetic database outage")
    values = dict(operation_id="price-outage", resource_type="meeting", resource_id="7", operation="intelligence",
                  provider="gemini", credential_source="user", metric="output_tokens", unit="token",
                  quantity=100, model="gemini-test", user_id=1, session_factory=outage,
                  occurred_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert record_event(**values) is None
    with db_context["session_factory"]() as db:
        import_prices(db, catalog(), apply=True)
        db.commit()
    assert reconcile_usage(apply=True, session_factory=db_context["session_factory"])["delivered"] == 1
    with db_context["session_factory"]() as db:
        row = db.query(UsageEvent).one()
        assert row.estimated_cost is None and row.price_id is None
        assert row.cost_reason == "price_lookup_unavailable"
