"""Retain account erasure receipts and Firebase cleanup intent."""
from alembic import op
import sqlalchemy as sa

revision = "20261013_0015"
down_revision = "20261009_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("account_deletions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("deleted_user_id", sa.Integer(), nullable=False),
        sa.Column("blocks_bootstrap", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("firebase_project_id", sa.String(128)),
        sa.Column("firebase_uid", sa.String(128)),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("deleted_user_id", name="uq_account_deletion_user"),
        sa.CheckConstraint("attempts >= 0", name="ck_account_deletion_attempts"),
        sa.CheckConstraint("(firebase_project_id IS NULL) = (firebase_uid IS NULL)", name="ck_account_deletion_identity_pair"),
        sa.CheckConstraint("completed_at IS NULL OR firebase_uid IS NULL", name="ck_account_deletion_completed"))
    op.create_index("ix_account_deletion_identity", "account_deletions", ["firebase_project_id", "firebase_uid"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM account_deletions")).scalar():
        raise RuntimeError("Preserve account deletion receipts and pending identity cleanup before downgrading")
    op.drop_index("ix_account_deletion_identity", table_name="account_deletions")
    op.drop_table("account_deletions")
