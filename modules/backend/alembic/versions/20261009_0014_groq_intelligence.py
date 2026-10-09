"""Add explicit Groq preference and retained platform authorization records."""
from alembic import op
import sqlalchemy as sa

revision = "20261009_0014"
down_revision = "20261008_0013"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_preferences_intelligence", "user_provider_preferences", type_="check")
    op.create_check_constraint("ck_preferences_intelligence", "user_provider_preferences",
                               "intelligence_provider IN ('automatic', 'gemini', 'groq')")
    op.create_table("intelligence_platform_calls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("intelligence_id", sa.Integer(), sa.ForeignKey("meeting_intelligence.id", ondelete="SET NULL"), unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("provider", sa.String(32), sa.ForeignKey("platform_provider_budgets.provider", ondelete="RESTRICT"), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("reserved_cents", sa.Integer(), nullable=False),
        sa.Column("input_token_bound", sa.Integer(), nullable=False),
        sa.Column("output_token_limit", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), server_default="reserved", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("reserved_cents > 0 AND input_token_bound > 0 AND output_token_limit > 0", name="ck_intelligence_call_amounts"),
        sa.CheckConstraint("state IN ('reserved', 'attempted')", name="ck_intelligence_call_state"))


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM intelligence_platform_calls")).scalar():
        raise RuntimeError("Preserve platform intelligence reservations before downgrading")
    if bind.execute(sa.text("SELECT count(*) FROM user_provider_preferences WHERE intelligence_provider = 'groq'")).scalar():
        raise RuntimeError("Resolve explicit Groq preferences before downgrading")
    op.drop_table("intelligence_platform_calls")
    op.drop_constraint("ck_preferences_intelligence", "user_provider_preferences", type_="check")
    op.create_check_constraint("ck_preferences_intelligence", "user_provider_preferences",
                               "intelligence_provider IN ('automatic', 'gemini')")
