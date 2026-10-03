"""Owner-scoped preferences, encrypted credentials and execution provenance."""
from alembic import op
import sqlalchemy as sa

revision = "20261002_0009"
down_revision = "20261002_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("user_provider_preferences",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("transcription_provider", sa.String(32), nullable=False, server_default="automatic"),
        sa.Column("intelligence_provider", sa.String(32), nullable=False, server_default="automatic"),
        sa.Column("use_diarization", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.CheckConstraint("transcription_provider IN ('automatic', 'whisper', 'assemblyai')", name="ck_preferences_transcription"),
        sa.CheckConstraint("intelligence_provider IN ('automatic', 'gemini')", name="ck_preferences_intelligence"))
    op.create_table("user_provider_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_provider_credential"),
        sa.CheckConstraint("provider IN ('assemblyai', 'gemini')", name="ck_user_provider_credential_provider"))
    for table in ("transcription_jobs", "meeting_intelligence"):
        op.add_column(table, sa.Column("credential_source", sa.String(16), nullable=False, server_default="platform"))
        op.add_column(table, sa.Column("credential_id", sa.String(36), nullable=True))
        op.add_column(table, sa.Column("credential_user_id", sa.Integer(), nullable=True))
        op.create_foreign_key(f"fk_{table}_credential", table, "user_provider_credentials", ["credential_id"], ["id"], ondelete="SET NULL")
        op.create_foreign_key(f"fk_{table}_credential_user", table, "users", ["credential_user_id"], ["id"], ondelete="SET NULL")
    op.add_column("transcription_jobs", sa.Column("provider_attempted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    # Retain encrypted credentials/settings and provenance unless explicitly exported.
    if op.get_bind().execute(sa.text("SELECT count(*) FROM user_provider_credentials")).scalar() or op.get_bind().execute(sa.text("SELECT count(*) FROM user_provider_preferences")).scalar():
        raise RuntimeError("Preserve provider credentials and preferences before downgrade")
    for table in ("meeting_intelligence", "transcription_jobs"):
        if op.get_bind().execute(sa.text(f"SELECT count(*) FROM {table} WHERE credential_source = 'user'")).scalar():
            raise RuntimeError("Preserve user execution provenance before downgrade")
    op.drop_column("transcription_jobs", "provider_attempted_at")
    for table in ("meeting_intelligence", "transcription_jobs"):
        op.drop_constraint(f"fk_{table}_credential_user", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table}_credential", table, type_="foreignkey")
        for column in ("credential_user_id", "credential_id", "credential_source"):
            op.drop_column(table, column)
    op.drop_table("user_provider_credentials")
    op.drop_table("user_provider_preferences")
