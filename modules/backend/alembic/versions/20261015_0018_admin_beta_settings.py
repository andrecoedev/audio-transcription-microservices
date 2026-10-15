"""Versioned, explicitly initialized operational policy; never activates spending."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261015_0018"
down_revision = "20261015_0017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("platform_provider_budgets", sa.Column("operational_policy", postgresql.JSONB(), nullable=True))
    op.add_column("platform_provider_budgets", sa.Column("configuration_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("platform_provider_budgets", sa.Column("price_version", sa.String(64), nullable=True))
    op.add_column("platform_provider_budgets", sa.Column("configuration_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("platform_provider_budgets", sa.Column("configuration_updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_platform_budget_config_actor", "platform_provider_budgets", "users", ["configuration_updated_by"], ["id"], ondelete="SET NULL")
    # A reduced cap is a future-authorization limit, never permission to rewrite
    # already committed use. Keep amounts nonnegative, remove only that coupling.
    op.drop_constraint("ck_platform_provider_budget_amounts", "platform_provider_budgets", type_="check")
    op.create_check_constraint("ck_platform_provider_budget_amounts", "platform_provider_budgets", "limit_cents >= 0 AND reserved_cents >= 0")


def downgrade():
    db = op.get_bind()
    if db.execute(sa.text("SELECT 1 FROM platform_provider_budgets WHERE operational_policy IS NOT NULL OR configuration_version > 0 OR reserved_cents > limit_cents LIMIT 1")).first():
        raise RuntimeError("Preserve operational policy and committed usage before downgrade")
    op.drop_constraint("ck_platform_provider_budget_amounts", "platform_provider_budgets", type_="check")
    op.create_check_constraint("ck_platform_provider_budget_amounts", "platform_provider_budgets", "limit_cents >= 0 AND reserved_cents >= 0 AND reserved_cents <= limit_cents")
    op.drop_constraint("fk_platform_budget_config_actor", "platform_provider_budgets", type_="foreignkey")
    for column in ("configuration_updated_by", "configuration_updated_at", "price_version", "configuration_version", "operational_policy"):
        op.drop_column("platform_provider_budgets", column)
