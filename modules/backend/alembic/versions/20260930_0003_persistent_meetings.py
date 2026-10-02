"""Add one meeting per completed transcription and renamable speakers.

Revision ID: 20260930_0003
Revises: 20260920_0002
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260930_0003"
down_revision: Union[str, None] = "20260920_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["id"], ["transcriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "meeting_speakers",
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("speaker_id", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("meeting_id", "speaker_id"),
    )

    # Existing completed results already have their full transcript in JSONB.
    # Backfill only metadata and stable speaker keys; do not copy transcript text.
    op.execute(
        """
        INSERT INTO meetings (id, title, language)
        SELECT id, original_filename, NULL
        FROM transcriptions
        WHERE status = 'completed'
        """
    )
    op.execute(
        """
        INSERT INTO meeting_speakers (meeting_id, speaker_id)
        SELECT DISTINCT t.id, segment.value ->> 'speaker'
        FROM transcriptions AS t
        CROSS JOIN LATERAL jsonb_array_elements(t.segments) AS segment(value)
        WHERE t.status = 'completed'
          AND segment.value ->> 'speaker' IS NOT NULL
          AND length(segment.value ->> 'speaker') BETWEEN 1 AND 100
        """
    )


def downgrade() -> None:
    op.drop_table("meeting_speakers")
    op.drop_table("meetings")
