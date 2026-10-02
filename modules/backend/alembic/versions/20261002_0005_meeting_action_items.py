"""Persist user-managed meeting actions independently from AI revisions."""

from alembic import op
import sqlalchemy as sa

revision = "20261002_0005"
down_revision = "20261001_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "meeting_action_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(4000), nullable=False),
        sa.Column("assignee", sa.String(255), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.CheckConstraint("status IN ('open', 'done', 'dismissed')", name="ck_meeting_action_items_status"),
        sa.CheckConstraint("length(trim(description)) > 0", name="ck_meeting_action_items_description"),
    )
    op.create_index("ix_meeting_action_items_meeting_id", "meeting_action_items", ["meeting_id"])


def downgrade():
    op.drop_index("ix_meeting_action_items_meeting_id", table_name="meeting_action_items")
    op.drop_table("meeting_action_items")
