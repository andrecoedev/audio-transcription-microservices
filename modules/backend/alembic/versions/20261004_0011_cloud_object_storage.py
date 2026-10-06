"""Add object storage keys and durable object deletion retries."""
from alembic import op
import sqlalchemy as sa


revision = "20261004_0011"
down_revision = "20261003_0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "transcription_jobs",
        sa.Column("input_object_key", sa.String(length=128), nullable=True),
    )
    op.create_table(
        "object_deletions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reference", sa.String(length=2048), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "attempts >= 0", name="ck_object_deletions_attempts_nonnegative"
        ),
        sa.UniqueConstraint("reference", name="uq_object_deletions_reference"),
    )


def downgrade():
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT count(*) FROM transcription_jobs WHERE input_object_key IS NOT NULL")
    ).scalar():
        raise RuntimeError("Preserve object storage keys before downgrade")
    if connection.execute(sa.text("SELECT count(*) FROM object_deletions")).scalar():
        raise RuntimeError("Preserve pending object deletions before downgrade")

    op.drop_table("object_deletions")
    op.drop_column("transcription_jobs", "input_object_key")
