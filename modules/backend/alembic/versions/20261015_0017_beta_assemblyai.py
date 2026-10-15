"""Preserve existing authorizations while adding round and financial metadata."""
from alembic import op
import sqlalchemy as sa

revision = "20261015_0017"
down_revision = "20261014_0016"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("beta_access_grants", "transcription_reservations"):
        op.add_column(table, sa.Column("round_id", sa.String(64), nullable=True))
        op.create_index(f"ix_{table}_round_id", table, ["round_id"])
    for table, columns in (("platform_provider_budgets", ("limit_cents", "reserved_cents")),
                           ("platform_provider_calls", ("reserved_cents",))):
        for name in columns:
            op.alter_column(table, name, existing_type=sa.Integer(), type_=sa.Numeric(24, 8),
                            existing_nullable=False, postgresql_using=f"{name}::numeric(24,8)")
    budget_columns = [
        sa.Column("alert_cents", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("alerted_at", sa.DateTime(timezone=True)),
        sa.Column("round_id", sa.String(64)),
        sa.Column("balance_cents", sa.Numeric(24, 8)),
        sa.Column("balance_baseline_cents", sa.Numeric(24, 8)),
        sa.Column("balance_checked_at", sa.DateTime(timezone=True)),
        sa.Column("balance_exclusive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("key_reference", sa.String(64)),
        sa.Column("project_reference", sa.String(64)),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.false()),
    ]
    call_columns = [
        sa.Column("operation_key", sa.String(100)),
        sa.Column("round_id", sa.String(64)), sa.Column("model", sa.String(64)),
        sa.Column("use_diarization", sa.Boolean()), sa.Column("price_version", sa.String(64)),
        sa.Column("hourly_rate_cents", sa.Numeric(24, 8)),
        sa.Column("remote_transcript_id", sa.String(128)), sa.Column("provider_status", sa.String(16)),
        sa.Column("provider_audio_seconds", sa.Numeric(20, 3)),
        sa.Column("estimated_cost_cents", sa.Numeric(24, 8)),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.Column("released_at", sa.DateTime(timezone=True)),
    ]
    for column in budget_columns:
        op.add_column("platform_provider_budgets", column)
    for column in call_columns:
        op.add_column("platform_provider_calls", column)
    op.execute("UPDATE platform_provider_calls SET operation_key = 'transcription:' || transcription_id::text WHERE transcription_id IS NOT NULL")
    op.create_unique_constraint("uq_platform_provider_calls_operation_key", "platform_provider_calls", ["operation_key"])


def downgrade():
    db = op.get_bind()
    # Never drop operational evidence or truncate fractional authorizations.
    for query in (
        "SELECT 1 FROM beta_access_grants WHERE round_id IS NOT NULL LIMIT 1",
        "SELECT 1 FROM transcription_reservations WHERE round_id IS NOT NULL LIMIT 1",
        "SELECT 1 FROM platform_provider_budgets WHERE balance_checked_at IS NOT NULL OR round_id IS NOT NULL OR reserved_cents <> trunc(reserved_cents) OR limit_cents <> trunc(limit_cents) LIMIT 1",
        "SELECT 1 FROM platform_provider_calls WHERE model IS NOT NULL OR remote_transcript_id IS NOT NULL OR provider_status IS NOT NULL OR settled_at IS NOT NULL OR released_at IS NOT NULL OR hourly_rate_cents IS NOT NULL OR reserved_cents <> trunc(reserved_cents) LIMIT 1",
    ):
        if db.execute(sa.text(query)).first():
            raise RuntimeError("Beta financial evidence exists; preserve it before downgrade")
    for column in ("released_at", "settled_at", "estimated_cost_cents", "provider_audio_seconds",
                   "provider_status", "remote_transcript_id", "hourly_rate_cents", "price_version",
                   "use_diarization", "model", "round_id"):
        op.drop_column("platform_provider_calls", column)
    op.drop_constraint("uq_platform_provider_calls_operation_key", "platform_provider_calls", type_="unique")
    op.drop_column("platform_provider_calls", "operation_key")
    for column in ("review_required", "project_reference", "key_reference", "balance_exclusive",
                   "balance_checked_at", "balance_baseline_cents", "balance_cents", "round_id",
                   "alerted_at", "alert_cents"):
        op.drop_column("platform_provider_budgets", column)
    for table, columns in (("platform_provider_budgets", ("limit_cents", "reserved_cents")),
                           ("platform_provider_calls", ("reserved_cents",))):
        for name in columns:
            op.alter_column(table, name, existing_type=sa.Numeric(24, 8), type_=sa.Integer(),
                            existing_nullable=False, postgresql_using=f"{name}::integer")
    for table in ("transcription_reservations", "beta_access_grants"):
        op.drop_index(f"ix_{table}_round_id", table_name=table)
        op.drop_column(table, "round_id")
