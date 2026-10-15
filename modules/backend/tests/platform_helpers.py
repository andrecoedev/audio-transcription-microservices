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
    from src.services.beta_settings import initialize_policy, read_policy, update_policy
    _, policy = read_policy(db)
    fresh = policy is None
    if fresh:
        initialize_policy(db, version=0, confirmed=True, actor_user_id=None)
    record_balance_check(db, available_usd=Decimal("50"), checked_at=now_utc(),
        key_reference=settings.AAI_PLATFORM_KEY_REFERENCE,
        project_reference=settings.AAI_PLATFORM_PROJECT_REFERENCE, exclusive=True, actor_user_id=None)
    if fresh:
        row, _ = read_policy(db)
        update_policy(db, section="assemblyai", changes={"assemblyai.hard_stop_usd": Decimal(settings.AAI_PLATFORM_BUDGET_CENTS) / 100,
            "assemblyai.alert_usd": Decimal(settings.AAI_PLATFORM_ALERT_CENTS) / 100, "assemblyai.platform_enabled": True},
            version=row.configuration_version, confirmed=True, actor_user_id=None)
        row, _ = read_policy(db)
        update_policy(db, section="beta", changes={"beta.enabled": True},
            version=row.configuration_version, confirmed=True, actor_user_id=None)
    db.commit()
