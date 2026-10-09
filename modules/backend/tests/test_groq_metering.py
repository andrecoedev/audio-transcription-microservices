"""Real token counts/Decimal estimates without overlapping billed categories."""
from decimal import Decimal

import pytest

from src.models import UsageEvent
from src.services.usage_metering import UsageRecorder, reconcile_usage
from src.services.usage_prices import import_prices


def _rates():
    return [dict(catalog_version="synthetic-groq-v1", provider="groq", model="openai/gpt-oss-20b",
        metric=metric, unit="token", currency="USD", unit_price="1", unit_quantity="1000000",
        effective_from="2026-01-01T00:00:00+00:00", effective_until=None,
        source="https://example.test/synthetic-rates") for metric in ("input_uncached_tokens", "output_tokens", "cache_read_tokens")]


def _recorder(factory, source="platform"):
    return UsageRecorder(operation_id="groq-token-fixture", user_id=1, resource_type="meeting", resource_id=1,
        operation="intelligence", provider="groq", credential_source=source,
        model="openai/gpt-oss-20b", session_factory=factory)


@pytest.mark.parametrize("source,scope", [("platform", "usagi"), ("user", "customer")])
def test_real_counts_priced_once_and_reasoning_not_double_billed(db_context, source, scope):
    factory = db_context["session_factory"]
    with factory() as db:
        import_prices(db, _rates(), apply=True)
        db.commit()
    recorder = _recorder(factory, source)
    event = {"status": "response", "prompt_tokens": 50, "completion_tokens": 30,
             "total_tokens": 80, "cached_tokens": 10, "reasoning_tokens": 20, "elapsed_seconds": 1.5}
    recorder.provider_response(event)
    recorder.provider_response(event)  # Observer delivery is idempotent, no repeated quantities.
    with factory() as db:
        events = {r.metric: r for r in db.query(UsageEvent)}
        assert events["input_tokens"].quantity == 50
        assert events["output_tokens"].quantity == 30
        assert events["reasoning_tokens"].quantity == 20
        priced = [r for r in events.values() if r.estimated_cost is not None]
        assert {r.metric for r in priced} == {"input_uncached_tokens", "output_tokens", "cache_read_tokens"}
        assert sum((r.estimated_cost for r in priced), Decimal(0)) == Decimal("0.000080")
        assert all(r.cost_scope == scope for r in priced)
        with pytest.raises(ValueError, match="Audit-only"):
            rate = _rates()[0]
            rate["metric"] = "reasoning_tokens"
            import_prices(db, [rate])


def test_missing_counts_remain_unknown_not_zero_and_journal_replays_without_provider(db_context):
    factory = db_context["session_factory"]
    def unavailable():
        raise OSError("synthetic unavailable database")
    _recorder(unavailable).provider_response({"status": "response", "completion_tokens": 12})
    assert reconcile_usage(apply=True, session_factory=factory)["failed"] == 0
    with factory() as db:
        events = {r.metric: r for r in db.query(UsageEvent)}
        assert events["input_tokens"].quantity is None
        assert events["cache_read_tokens"].quantity is None
        assert events["input_uncached_tokens"].quantity is None
        assert events["output_tokens"].quantity == 12
        assert all(r.estimated_cost is None for r in events.values())
