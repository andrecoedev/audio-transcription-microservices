"""Add usage ledger and immutable price catalog without altering domain data."""
from alembic import op
import sqlalchemy as sa

revision = "20261007_0012"
down_revision = "20261004_0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transcription_jobs", sa.Column("usage_attempt_id", sa.String(36), nullable=True))
    op.add_column("meeting_intelligence", sa.Column("usage_attempt_id", sa.String(36), nullable=True))
    # The explicit table definitions are frozen here, independent of future models.
    op.create_table(
        "usage_prices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("catalog_version", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("unit_price", sa.Numeric(30, 12), nullable=False),
        sa.Column("unit_quantity", sa.Numeric(30, 9), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True)),
        sa.Column("source", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("unit_price >= 0 AND unit_quantity > 0", name="ck_usage_price_amounts"),
        sa.CheckConstraint("effective_until IS NULL OR effective_until > effective_from", name="ck_usage_price_period"),
        sa.UniqueConstraint("catalog_version", "provider", "model", "metric", "unit", name="uq_usage_price_version_metric"),
    )
    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("operation_id", sa.String(100), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("guest_session_id", sa.String(36)),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("credential_source", sa.String(16), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Numeric(30, 9)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("measurement_source", sa.String(32), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("use_diarization", sa.Boolean()),
        sa.Column("price_id", sa.String(36), sa.ForeignKey("usage_prices.id", ondelete="RESTRICT")),
        sa.Column("currency", sa.String(3)),
        sa.Column("estimated_cost", sa.Numeric(30, 12)),
        sa.Column("cost_scope", sa.String(16), nullable=False),
        sa.Column("cost_reason", sa.String(64), nullable=False),
        sa.CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_usage_quantity"),
        sa.CheckConstraint("estimated_cost IS NULL OR estimated_cost >= 0", name="ck_usage_cost"),
        sa.CheckConstraint("credential_source IN ('user', 'platform', 'local', 'none')", name="ck_usage_source"),
        sa.CheckConstraint("status IN ('started', 'completed', 'failed', 'cancelled', 'unknown')", name="ck_usage_status"),
    )
    op.create_index("ix_usage_owner_time", "usage_events", ["user_id", "occurred_at"])
    op.create_index("ix_usage_operation", "usage_events", ["operation_id"])
    op.create_index("ix_usage_guest", "usage_events", ["guest_session_id"])


def downgrade():
    for table in ("usage_events", "usage_prices"):
        if op.get_bind().execute(sa.text(f"SELECT count(*) FROM {table}")).scalar():
            raise RuntimeError("Export and preserve usage history before downgrade")
    op.drop_table("usage_events")
    op.drop_table("usage_prices")
    op.drop_column("meeting_intelligence", "usage_attempt_id")
    op.drop_column("transcription_jobs", "usage_attempt_id")
