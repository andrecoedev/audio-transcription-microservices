"""Durable platform spending reservations and no-repeat provenance."""
from alembic import op
import sqlalchemy as sa

revision = "20261002_0008"
down_revision = "20261002_0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("platform_provider_budgets",
        sa.Column("provider", sa.String(32), primary_key=True),
        sa.Column("limit_cents", sa.Integer(), nullable=False),
        sa.Column("reserved_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("limit_cents >= 0 AND reserved_cents >= 0 AND reserved_cents <= limit_cents",
                           name="ck_platform_provider_budget_amounts"))
    op.create_table("platform_provider_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transcription_id", sa.Integer(), sa.ForeignKey("transcriptions.id", ondelete="SET NULL"), unique=True),
        sa.Column("provider", sa.String(32), sa.ForeignKey("platform_provider_budgets.provider", ondelete="RESTRICT"), nullable=False),
        sa.Column("context", sa.String(16), nullable=False),
        sa.Column("credential_source", sa.String(16), nullable=False, server_default="platform"),
        sa.Column("reserved_cents", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="reserved"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("reserved_cents > 0", name="ck_platform_provider_call_amount"),
        sa.CheckConstraint("context IN ('guest', 'local')", name="ck_platform_provider_call_context"),
        sa.CheckConstraint("state IN ('reserved', 'attempted')", name="ck_platform_provider_call_state"))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM platform_provider_calls")).scalar():
        raise RuntimeError("Preserve platform spending records before downgrade")
    op.drop_table("platform_provider_calls")
    op.drop_table("platform_provider_budgets")
