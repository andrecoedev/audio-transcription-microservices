"""Operator-only append-only catalog import. No defaults, conversion or billing."""
import re
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import uuid5

from ..models import UsagePrice
from .usage_metering import _NAMESPACE, _PRICEABLE, decimal_quantity, utc


def import_prices(db, rows, *, apply=False):
    if not isinstance(rows, list) or not rows or len(rows) > 1000:
        raise ValueError("Price catalog must contain 1-1000 rates")
    allowed = {"catalog_version", "provider", "model", "metric", "unit", "currency",
               "unit_price", "unit_quantity", "effective_from", "effective_until", "source"}
    prepared = []
    identities = set()
    for row in rows:
        if set(row) != allowed:
            raise ValueError("Price catalog fields do not match the contract")
        data = dict(row)
        for key, maximum in (("catalog_version", 64), ("provider", 32), ("model", 100), ("metric", 64), ("unit", 32)):
            if not isinstance(data[key], str) or len(data[key]) > maximum or not re.fullmatch(r"[A-Za-z0-9_.:+-]+", data[key]):
                raise ValueError("Invalid catalog label")
        if data["metric"] not in _PRICEABLE:
            raise ValueError("Audit-only metric cannot be priced")
        if data["provider"] not in {"assemblyai", "gemini", "whisper", "object_storage"}:
            raise ValueError("Unsupported pricing provider")
        expected_unit = "token" if data["metric"].endswith("tokens") else "byte_second" if data["metric"] == "byte_seconds" else "second"
        if data["unit"] != expected_unit or not re.fullmatch(r"[A-Z]{3}", data["currency"]):
            raise ValueError("Invalid pricing unit or currency")
        # Require explicit source without query credentials or embedded auth.
        source = urlsplit(data["source"])
        if len(data["source"]) > 500 or source.scheme != "https" or not source.hostname or source.username or source.password or source.query or source.fragment:
            raise ValueError("Pricing source must be an HTTPS reference without credentials/query")
        # Monetary inputs must be strings, never already-rounded JSON floats.
        if not isinstance(data["unit_price"], str) or not isinstance(data["unit_quantity"], str):
            raise ValueError("Price and quantity must be decimal strings")
        data["unit_price"] = Decimal(data["unit_price"])
        if not data["unit_price"].is_finite() or data["unit_price"] < 0 or data["unit_price"] >= Decimal("1e18") or data["unit_price"].as_tuple().exponent < -12:
            raise ValueError("Invalid monetary precision/range")
        data["unit_quantity"] = decimal_quantity(data["unit_quantity"])
        if data["unit_quantity"] <= 0:
            raise ValueError("Price unit quantity must be positive")
        for key in ("effective_from", "effective_until"):
            value = datetime.fromisoformat(data[key]) if data[key] is not None else None
            if value is not None and value.tzinfo is None:
                raise ValueError("Price dates require a timezone")
            data[key] = utc(value) if value is not None else None
        if data["effective_from"] is None or (data["effective_until"] and data["effective_until"] <= data["effective_from"]):
            raise ValueError("Invalid pricing period")
        identity = "/".join(data[key] for key in ("catalog_version", "provider", "model", "metric", "unit"))
        if identity in identities:
            raise ValueError("Duplicate rate in catalog")
        identities.add(identity)
        data["id"] = str(uuid5(_NAMESPACE, "price/" + identity))
        existing = db.get(UsagePrice, data["id"])
        if existing:
            for key, value in data.items():
                persisted = getattr(existing, key)
                if isinstance(persisted, datetime):
                    persisted = utc(persisted)
                if persisted != value:
                    raise ValueError("Existing catalog rate is immutable; create a new version")
        else:
            prepared.append(data)
    if apply:
        for data in prepared:
            db.add(UsagePrice(**data))
        db.flush()
    return {"rates": len(rows), "new": len(prepared), "dry_run": not apply}
