"""Create the initial PostgreSQL application schema.

Revision ID: 20260909_0001
Revises: None
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260909_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transcriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_size_mb", sa.Float(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("transcription_model", sa.String(length=50), nullable=False),
        sa.Column("use_diarization", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("segments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("num_speakers", sa.Integer(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("processing_time_seconds", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("file_size_mb >= 0", name="ck_transcriptions_file_size_nonnegative"),
        sa.CheckConstraint("duration_seconds >= 0", name="ck_transcriptions_duration_nonnegative"),
        sa.CheckConstraint(
            "processing_time_seconds IS NULL OR processing_time_seconds >= 0",
            name="ck_transcriptions_processing_time_nonnegative",
        ),
        sa.CheckConstraint(
            "num_speakers IS NULL OR num_speakers >= 0",
            name="ck_transcriptions_num_speakers_nonnegative",
        ),
        sa.CheckConstraint(
            "word_count IS NULL OR word_count >= 0",
            name="ck_transcriptions_word_count_nonnegative",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_transcriptions_status",
        ),
    )
    op.create_index(
        "ix_transcriptions_status_created_at",
        "transcriptions",
        ["status", "created_at"],
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "transcription_owners",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transcription_id", sa.Integer(), nullable=False),
        sa.Column("owner_sub", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["transcription_id"], ["transcriptions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "transcription_id", name="uq_transcription_owners_transcription_id"
        ),
    )
    op.create_index(
        "ix_transcription_owners_owner_sub", "transcription_owners", ["owner_sub"]
    )

    op.create_table(
        "transcription_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transcription_id", sa.Integer(), nullable=False),
        sa.Column("input_path", sa.String(length=500), nullable=False),
        sa.Column("use_diarization", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("transcription_model", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_transcription_jobs_status",
        ),
        sa.ForeignKeyConstraint(
            ["transcription_id"], ["transcriptions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "transcription_id", name="uq_transcription_jobs_transcription_id"
        ),
    )
    op.create_index(
        "ix_transcription_jobs_status_created_at",
        "transcription_jobs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_transcription_jobs_status_created_at", table_name="transcription_jobs")
    op.drop_table("transcription_jobs")
    op.drop_index("ix_transcription_owners_owner_sub", table_name="transcription_owners")
    op.drop_table("transcription_owners")
    op.drop_table("users")
    op.drop_index("ix_transcriptions_status_created_at", table_name="transcriptions")
    op.drop_table("transcriptions")
