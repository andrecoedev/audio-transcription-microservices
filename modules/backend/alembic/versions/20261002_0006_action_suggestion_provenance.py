"""Track immutable AI suggestion provenance and review dispositions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261002_0006"
down_revision = "20261002_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("meeting_action_items", sa.Column("source_intelligence_id", sa.Integer(), nullable=True))
    op.add_column("meeting_action_items", sa.Column("source_revision", sa.Integer(), nullable=True))
    op.add_column("meeting_action_items", sa.Column("source_index", sa.Integer(), nullable=True))
    op.add_column("meeting_action_items", sa.Column("original_description", sa.String(4000), nullable=True))
    op.add_column("meeting_action_items", sa.Column("original_assignee", sa.String(255), nullable=True))
    op.add_column("meeting_action_items", sa.Column("original_due_date", sa.String(255), nullable=True))
    op.add_column("meeting_action_items", sa.Column("evidence", postgresql.JSONB(), nullable=True))
    op.create_foreign_key(
        "fk_meeting_action_items_source_intelligence_id", "meeting_action_items",
        "meeting_intelligence", ["source_intelligence_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_table(
        "meeting_action_suggestion_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("source_intelligence_id", sa.Integer(), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("source_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("action_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], name="fk_meeting_action_suggestion_reviews_meeting_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_intelligence_id"], ["meeting_intelligence.id"], name="fk_meeting_action_suggestion_reviews_intelligence_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["action_id"], ["meeting_action_items.id"], name="fk_meeting_action_suggestion_reviews_action_id", ondelete="SET NULL"),
        sa.UniqueConstraint("meeting_id", "source_revision", "source_index", name="uq_meeting_action_suggestion_review_source"),
        sa.CheckConstraint("status IN ('accepted', 'dismissed', 'deleted')", name="ck_meeting_action_suggestion_review_status"),
        sa.CheckConstraint("(status = 'accepted' AND action_id IS NOT NULL) OR (status != 'accepted' AND action_id IS NULL)", name="ck_meeting_action_suggestion_review_action"),
    )
    op.create_index("ix_meeting_action_suggestion_reviews_meeting_id", "meeting_action_suggestion_reviews", ["meeting_id"])


def downgrade():
    op.drop_index("ix_meeting_action_suggestion_reviews_meeting_id", table_name="meeting_action_suggestion_reviews")
    op.drop_table("meeting_action_suggestion_reviews")
    op.drop_constraint("fk_meeting_action_items_source_intelligence_id", "meeting_action_items", type_="foreignkey")
    for column in ("evidence", "original_due_date", "original_assignee", "original_description", "source_index", "source_revision", "source_intelligence_id"):
        op.drop_column("meeting_action_items", column)
