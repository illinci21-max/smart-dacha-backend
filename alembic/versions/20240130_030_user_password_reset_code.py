"""Add password reset code fields to users.

Revision ID: 030_user_password_reset_code
Revises: 029_profile_protection_catalog
"""
from alembic import op
import sqlalchemy as sa

revision = "030_user_password_reset_code"
down_revision = "029_profile_protection_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_reset_code_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("password_reset_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "password_reset_expires_at")
    op.drop_column("users", "password_reset_code_hash")
