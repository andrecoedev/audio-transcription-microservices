"""Add persistent ownership and minimal audit events.

Revision ID: 20260920_0002
Revises: 20260909_0001
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260920_0002"
down_revision: Union[str, None] = "20260909_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transcription_owners",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_transcription_owners_user_id_users",
        "transcription_owners",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_transcription_owners_user_id",
        "transcription_owners",
        ["user_id"],
    )

    # Exact, unique username matches are safe. Unmatched legacy subjects stay
    # NULL and can be reported/reconciled later; no data is guessed.
    op.execute(
        """
        UPDATE transcription_owners AS ownership
        SET user_id = users.id
        FROM users
        WHERE ownership.owner_sub = users.username
          AND ownership.user_id IS NULL
        """
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "actor_type",
            sa.String(length=20),
            server_default=sa.text("'system'"),
            nullable=False,
        ),
        sa.Column("event", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=True),
        sa.Column("resource_id", sa.String(length=100), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"])
    op.create_index(
        "ix_audit_events_event_timestamp", "audit_events", ["event", "timestamp"]
    )
    op.create_index(
        "ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_actor_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_event_timestamp", table_name="audit_events")
    op.drop_index("ix_audit_events_timestamp", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_transcription_owners_user_id", table_name="transcription_owners")
    op.drop_constraint(
        "fk_transcription_owners_user_id_users",
        "transcription_owners",
        type_="foreignkey",
    )
    op.drop_column("transcription_owners", "user_id")
