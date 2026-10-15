"""Explicit synthetic operational funding; never bypass production admission."""
from decimal import Decimal

from src.config import settings
from src.services.platform_budget import now_utc, record_balance_check


def configure_platform(monkeypatch, *, limit=1500):
    for key, value in {
        "AAI_PLATFORM_ENABLED": True, "AAI_API_KEY_CONFIGURED": True,
        "AAI_PLATFORM_BUDGET_CENTS": limit, "AAI_PLATFORM_ALERT_CENTS": 0,
        "AAI_PLATFORM_HOURLY_USD": Decimal("0.23"),
        "AAI_PLATFORM_PRICE_VERSION": "synthetic-price-version",
        "AAI_PLATFORM_KEY_REFERENCE": "synthetic-key-label",
        "AAI_PLATFORM_PROJECT_REFERENCE": "synthetic-project-label",
        "AAI_BETA_ROUND_ID": "test-round",
    }.items():
        monkeypatch.setattr(settings, key, value)


def confirm_test_balance(db):
    record_balance_check(db, available_usd=Decimal("50"), checked_at=now_utc(),
        key_reference=settings.AAI_PLATFORM_KEY_REFERENCE,
        project_reference=settings.AAI_PLATFORM_PROJECT_REFERENCE, exclusive=True, actor_user_id=None)
    db.commit()
