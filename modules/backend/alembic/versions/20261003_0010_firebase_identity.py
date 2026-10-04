"""Bind Firebase identities to internal users."""
from alembic import op
import sqlalchemy as sa

revision = "20261003_0010"
down_revision = "20261002_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=True)
    op.create_table(
        "firebase_identities",
        sa.Column("project_id", sa.String(128), primary_key=True),
        sa.Column("uid", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_firebase_identity_user"),
    )


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT count(*) FROM firebase_identities")).scalar():
        raise RuntimeError("Preserve Firebase identity bindings before downgrade")
    if connection.execute(sa.text("SELECT count(*) FROM users WHERE hashed_password IS NULL")).scalar():
        raise RuntimeError("Preserve passwordless users before downgrade")

    op.drop_table("firebase_identities")
    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=False)
