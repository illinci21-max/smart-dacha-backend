"""Add missing firebase token column to users.

Revision ID: 022_user_firebase_token
Revises: 021_composite_indexes
"""
from alembic import op


revision = "022_user_firebase_token"
down_revision = "021_composite_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS firebase_token VARCHAR(1000)")


def downgrade() -> None:
    op.drop_column("users", "firebase_token")
