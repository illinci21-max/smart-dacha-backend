"""Add admin flag to users.

Revision ID: 011_user_admin
Revises: 010_profile_confidence
"""

from alembic import op
import sqlalchemy as sa


revision = "011_user_admin"
down_revision = "010_profile_confidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("users")}
    if "is_admin" not in columns:
        op.add_column(
            "users",
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("users")}
    if "is_admin" in columns:
        op.drop_column("users", "is_admin")
