"""Content-free measurements, immutable estimates and durable idempotent replay.

The journal lives on the existing private runtime volume, NOT in Redis. Failed
delivery is retried without invoking a provider. Financial values never use float.
"""
import json
import logging
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..database import SessionLocal
from ..models import GuestSession, UsageEvent, UsagePrice, User

logger = logging.getLogger(__name__)
_NAMESPACE = UUID("b4f6d335-c484-4968-94d5-d8fa1372879c")
_LABEL = re.compile(r"[A-Za-z0-9_.:-]{1,100}\Z")
_PRICEABLE = {"provider_audio_seconds", "input_uncached_tokens", "output_tokens",
              "thinking_tokens", "cache_read_tokens", "tool_tokens", "processing_seconds", "byte_seconds"}


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def decimal_quantity(value):
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid usage quantity") from None
    if not number.is_finite() or number < 0 or number >= Decimal("1e21"):
        raise ValueError("Invalid usage quantity")
    return number.quantize(Decimal("0.000000001"))


def event_id(operation_id, metric, phase):
    return str(uuid5(_NAMESPACE, f"{operation_id}/{metric}/{phase}"))


def spool_directory():
    path = Path(settings.USAGE_SPOOL_DIRECTORY)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path


def _freeze_cost(db, data):
    data.update(price_id=None, currency=None, estimated_cost=None,
                cost_scope="unknown", cost_reason="no_configured_price")
    if data["metric"] not in _PRICEABLE:
        data["cost_reason"] = "technical_measurement_only"
        return
    if data["quantity"] is None:
        data["cost_reason"] = "quantity_unknown"
        return
    if data["status"] != "completed" and data["metric"] != "processing_seconds":
        data["cost_reason"] = "provider_billing_unknown"
        return
    # AAI speaker detection can change the tariff. Never apply a base-only rate.
    model = data["model"] + ("+speakers" if data["provider"] == "assemblyai" and data["use_diarization"] else "")
    when = datetime.fromisoformat(data["occurred_at"])
    rates = db.query(UsagePrice).filter_by(provider=data["provider"], model=model,
                                          metric=data["metric"], unit=data["unit"]).all()
    matches = [r for r in rates if utc(r.effective_from) <= when and
               (r.effective_until is None or when < utc(r.effective_until))]
    if not matches:
        return
    # Catalog versions can supersede earlier versions only from their own start.
    matches.sort(key=lambda r: utc(r.effective_from), reverse=True)
    if len(matches) > 1 and utc(matches[0].effective_from) == utc(matches[1].effective_from):
        data["cost_reason"] = "ambiguous_price"
        return
    rate = matches[0]
    amount = (Decimal(data["quantity"]) * rate.unit_price / rate.unit_quantity).quantize(Decimal("0.000000000001"))
    data.update(price_id=rate.id, currency=rate.currency, estimated_cost=str(amount),
                cost_scope="customer" if data["credential_source"] == "user" else "usagi",
                cost_reason="configured_estimate_not_invoice")


def _journal(data):
    root = spool_directory()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = root / (data["id"] + ".json")
    # Each event is prepared once; replay never selects newer prices or timestamps.
    if target.exists():
        return target, _read_journal(target)
    temporary = root / (data["id"] + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            json.dump(data, handle, separators=(",", ":"), allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        # Hard link is atomic and refuses to overwrite another producer's event.
        try:
            os.link(temporary, target)
        except FileExistsError:
            data = _read_journal(target)
        if os.name != "nt":
            descriptor = os.open(root, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)
    return target, data


def _read_journal(path):
    if path.is_symlink() or path.stat().st_size > 16384:
        raise ValueError("Invalid usage journal")
    data = json.loads(path.read_text(encoding="utf-8"))
    expected = set(UsageEvent.__table__.columns.keys()) - {"recorded_at"}
    if set(data) != expected or str(UUID(data["id"])) + ".json" != path.name:
        raise ValueError("Invalid usage journal fields")
    for field in ("operation_id", "resource_type", "resource_id", "operation", "provider", "metric", "unit", "measurement_source"):
        if not isinstance(data[field], str) or not _LABEL.fullmatch(data[field]):
            raise ValueError("Invalid usage journal label")
    if data["credential_source"] not in {"user", "platform", "local", "none"} or data["status"] not in {"started", "completed", "failed", "cancelled", "unknown"}:
        raise ValueError("Invalid usage journal state")
    decimal_quantity(data["quantity"])
    return data


def persist_event(db, data):
    """A unique ID makes concurrent/repeated delivery a no-op; never reprice."""
    if db.get(UsageEvent, data["id"]) is not None:
        return False
    values = dict(data)
    values["occurred_at"] = datetime.fromisoformat(values["occurred_at"])
    for field in ("quantity", "estimated_cost"):
        values[field] = Decimal(values[field]) if values[field] is not None else None
    # Replayed events must not resurrect deleted users or steal a Guest context.
    if values["guest_session_id"]:
        guest = db.get(GuestSession, values["guest_session_id"])
        values["user_id"] = guest.claimed_by_user_id if guest else None
    if values["user_id"] is not None and db.get(User, values["user_id"]) is None:
        values["user_id"] = None
    try:
        with db.begin_nested():
            db.add(UsageEvent(**values))
            db.flush()
    except IntegrityError:
        if db.get(UsageEvent, data["id"]) is None:
            raise
        return False
    return True


def record_event(*, operation_id, resource_type, resource_id, operation, provider,
                 credential_source, metric, unit, quantity=None, status="completed",
                 phase="observed", user_id=None, guest_session_id=None,
                 measurement_source="application", model="", use_diarization=None,
                 session_factory=None, occurred_at=None, pricing_session=None, journal_only=False):
    """Best-effort delivery, durable intent. Never interrupt a product result."""
    factory = session_factory or SessionLocal
    try:
        quantity = decimal_quantity(quantity)
        data = dict(id=event_id(operation_id, metric, phase), operation_id=str(operation_id),
                    user_id=user_id, guest_session_id=guest_session_id,
                    resource_type=resource_type, resource_id=str(resource_id), operation=operation,
                    provider=provider, credential_source=credential_source, metric=metric,
                    unit=unit, quantity=str(quantity) if quantity is not None else None,
                    status=status, occurred_at=utc(occurred_at or datetime.now(timezone.utc)).isoformat(),
                    measurement_source=measurement_source, model=model, use_diarization=use_diarization)
        # Frozen unknown if price lookup is unavailable; replay cannot invent cost.
        data.update(price_id=None, currency=None, estimated_cost=None,
                    cost_scope="unknown", cost_reason="price_lookup_unavailable")
        try:
            if pricing_session is not None:
                _freeze_cost(pricing_session, data)
            else:
                with factory() as db:
                    _freeze_cost(db, data)
        except Exception as exc:
            logger.warning("Usage pricing unavailable (%s)", type(exc).__name__)
        path, data = _journal(data)
        if journal_only:
            return data["id"]
        with factory() as db:
            persist_event(db, data)
            db.commit()
        path.unlink(missing_ok=True)
        return data["id"]
    except Exception as exc:
        logger.error("Usage delivery deferred; reconcile private journal (%s)", type(exc).__name__)
        return None


def reconcile_usage(*, apply=False, limit=1000, session_factory=None):
    factory = session_factory or SessionLocal
    result = {"pending": 0, "delivered": 0, "failed": 0}
    root = spool_directory()
    if not root.exists():
        return result
    for path in sorted(root.glob("*.json"))[:limit]:
        result["pending"] += 1
        try:
            data = _read_journal(path)
            if apply:
                with factory() as db:
                    persist_event(db, data)
                    db.commit()
                path.unlink(missing_ok=True)
                result["delivered"] += 1
        except FileNotFoundError:
            pass  # Another reconciler already committed and removed this entry.
        except Exception as exc:
            logger.warning("Usage replay failed (%s)", type(exc).__name__)
            result["failed"] += 1
    return result


class UsageRecorder:
    """Per-attempt context, shared by worker stages; no provider secrets."""
    def __init__(self, **context):
        self.context = context

    def record(self, metric, unit, quantity=None, **kwargs):
        return record_event(**self.context, metric=metric, unit=unit, quantity=quantity, **kwargs)

    def provider_response(self, event):
        provider = self.context["provider"]
        if provider == "assemblyai":
            phase = event.get("phase", "polled")
            status = {"completed": "completed", "error": "failed"}.get(event.get("status"), "unknown")
            self.record("external_call" if phase == "submitted" else "provider_state",
                        "call" if phase == "submitted" else "state", 1 if phase == "submitted" else None,
                        phase=phase, status=status, measurement_source="provider_response")
            if phase != "submitted":
                self.record("provider_audio_seconds", "second", event.get("audio_duration_seconds"),
                            status=status, measurement_source="provider_response")
        elif provider == "gemini":
            status = "completed" if event.get("status") == "response" else "unknown"
            for key, metric in (("prompt_tokens", "input_tokens"), ("candidates_tokens", "output_tokens"),
                                ("total_tokens", "total_tokens"), ("thoughts_tokens", "thinking_tokens"),
                                ("cached_tokens", "cache_read_tokens"), ("tool_use_prompt_tokens", "tool_tokens")):
                self.record(metric, "token", event.get(key), status=status, measurement_source="provider_response")
            prompt, cached = event.get("prompt_tokens"), event.get("cached_tokens")
            uncached = prompt - cached if isinstance(prompt, int) and isinstance(cached, int) and 0 <= cached <= prompt else None
            self.record("input_uncached_tokens", "token", uncached, status=status, measurement_source="derived_provider_counts")
            self.record("provider_latency_seconds", "second", event.get("elapsed_seconds"), status=status)
