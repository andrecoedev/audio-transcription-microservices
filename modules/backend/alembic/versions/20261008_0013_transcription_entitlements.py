"""Add account plans, beta grants, and durable transcription reservations.

Revision ID: 20261008_0013
Revises: 20261007_0012
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261008_0013"
down_revision = "20261007_0012"
branch_labels = None
depends_on = None


def upgrade():
    # Existing accounts are explicitly placed on the free plan; the server
    # default also covers accounts inserted by older application versions.
    op.add_column(
        "users",
        sa.Column("plan", sa.String(length=16), server_default="free", nullable=False),
    )
    op.create_check_constraint(
        "ck_users_plan", "users", "plan IN ('free', 'starter', 'business')"
    )

    op.create_table(
        "beta_access_grants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "granted_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "capabilities",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_beta_access_grants_user_id", "beta_access_grants", ["user_id"]
    )

    op.create_table(
        "transcription_reservations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("operation_key", sa.String(length=100), nullable=False),
        sa.Column(
            "transcription_id",
            sa.Integer(),
            sa.ForeignKey("transcriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("credential_source", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("reserved_seconds", sa.Numeric(precision=20, scale=3), nullable=False),
        sa.Column("measured_seconds", sa.Numeric(precision=20, scale=3), nullable=True),
        sa.Column("stored_bytes", sa.Integer(), nullable=False),
        sa.Column("input_reference", sa.String(length=500), nullable=False),
        sa.Column("storage_released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("source IN ('usagi', 'byok')", name="ck_reservation_source"),
        sa.CheckConstraint(
            "state IN ('queued', 'processing', 'started', 'consumed', 'released', 'unknown')",
            name="ck_reservation_state",
        ),
        sa.CheckConstraint(
            "reserved_seconds >= 0 AND stored_bytes >= 0",
            name="ck_reservation_amounts",
        ),
        sa.UniqueConstraint(
            "operation_key", name="uq_transcription_reservation_operation"
        ),
        sa.UniqueConstraint(
            "transcription_id", name="uq_transcription_reservation_resource"
        ),
    )
    op.create_index(
        "ix_reservation_owner_period",
        "transcription_reservations",
        ["user_id", "period_start"],
    )


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT count(*) FROM beta_access_grants")).scalar():
        raise RuntimeError("Preserve beta access grants before downgrading")
    if connection.execute(
        sa.text("SELECT count(*) FROM transcription_reservations")
    ).scalar():
        raise RuntimeError("Preserve transcription reservations before downgrading")
    if connection.execute(
        sa.text("SELECT count(*) FROM users WHERE plan != 'free'")
    ).scalar():
        raise RuntimeError("Move all accounts to the free plan before downgrading")

    op.drop_index(
        "ix_reservation_owner_period", table_name="transcription_reservations"
    )
    op.drop_table("transcription_reservations")
    op.drop_index("ix_beta_access_grants_user_id", table_name="beta_access_grants")
    op.drop_table("beta_access_grants")
    op.drop_constraint("ck_users_plan", "users", type_="check")
    op.drop_column("users", "plan")
