"""Persist explicit development-only local transcription access."""
from alembic import op
import sqlalchemy as sa

revision = "20261014_0016"
down_revision = "20261013_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("development_local_access", sa.Boolean(),
                  server_default=sa.text("false"), nullable=False))
    op.alter_column("transcription_reservations", "stored_bytes",
        existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=False)


def downgrade():
    maximum = op.get_bind().execute(sa.text(
        "SELECT max(stored_bytes) FROM transcription_reservations")).scalar_one()
    if maximum is not None and maximum > 2147483647:
        raise RuntimeError("Cannot downgrade stored_bytes values above the Integer range")
    op.drop_column("users", "development_local_access")
    op.alter_column("transcription_reservations", "stored_bytes",
        existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=False)
