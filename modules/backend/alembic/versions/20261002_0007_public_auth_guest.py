"""Public registration provenance and expiring guest ownership.

Revision ID: 20261002_0007
Revises: 20261002_0006
"""
from alembic import op
import sqlalchemy as sa

revision = "20261002_0007"
down_revision = "20261002_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("registration_source", sa.String(16), nullable=False, server_default="local"))
    op.create_check_constraint("ck_users_registration_source", "users", "registration_source IN ('local', 'public')")
    op.create_table("guest_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("jobs_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("jobs_created >= 0", name="ck_guest_sessions_jobs_created"))
    op.create_index("ix_guest_sessions_expires_at", "guest_sessions", ["expires_at"])
    op.add_column("transcription_owners", sa.Column("guest_session_id", sa.String(36), sa.ForeignKey("guest_sessions.id", ondelete="RESTRICT")))
    op.create_index("ix_transcription_owners_guest_session_id", "transcription_owners", ["guest_session_id"])
    op.create_check_constraint("ck_transcription_owners_single_context", "transcription_owners", "guest_session_id IS NULL OR user_id IS NULL")
    op.add_column("transcription_jobs", sa.Column("max_duration_seconds", sa.Integer()))
    op.add_column("transcription_jobs", sa.Column("timeout_seconds", sa.Integer()))


def downgrade():
    # Never silently turn guest-owned data into unresolvable legacy ownership.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT count(*) FROM users WHERE registration_source = 'public'")).scalar():
        raise RuntimeError("Public accounts require an explicit preservation plan before downgrading")
    if connection.execute(sa.text("SELECT count(*) FROM transcription_owners WHERE guest_session_id IS NOT NULL")).scalar():
        raise RuntimeError("Claim or explicitly erase guest results before downgrading")
    op.drop_column("transcription_jobs", "timeout_seconds")
    op.drop_column("transcription_jobs", "max_duration_seconds")
    op.drop_index("ix_transcription_owners_guest_session_id", table_name="transcription_owners")
    op.drop_constraint("ck_transcription_owners_single_context", "transcription_owners", type_="check")
    op.drop_column("transcription_owners", "guest_session_id")
    op.drop_index("ix_guest_sessions_expires_at", table_name="guest_sessions")
    op.drop_table("guest_sessions")
    op.drop_constraint("ck_users_registration_source", "users", type_="check")
    op.drop_column("users", "registration_source")
