"""Persist versioned meeting intelligence.

Revision ID: 20261001_0004
Revises: 20260930_0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261001_0004"
down_revision = "20260930_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "meeting_intelligence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("meeting_id", "revision", name="uq_intelligence_meeting_revision"),
        sa.CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')", name="ck_intelligence_status"),
        sa.CheckConstraint("revision > 0", name="ck_intelligence_revision"),
        sa.CheckConstraint("status != 'completed' OR result IS NOT NULL", name="ck_intelligence_completed_result"),
    )
    op.create_index("ix_intelligence_one_active", "meeting_intelligence", ["meeting_id"], unique=True,
                    postgresql_where=sa.text("status IN ('pending', 'processing')"))


def downgrade():
    op.drop_index("ix_intelligence_one_active", table_name="meeting_intelligence")
    op.drop_table("meeting_intelligence")
