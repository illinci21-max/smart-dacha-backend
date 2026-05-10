"""Unlock Free tier feature limits.

Revision ID: 024_unlock_free_tier_limits
Revises: 023_forum_tables
"""
from alembic import op


revision = "024_unlock_free_tier_limits"
down_revision = "023_forum_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET plots_limit = GREATEST(plots_limit, 999),
            plants_limit = GREATEST(plants_limit, 9999)
        WHERE subscription_tier = 'free'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET plots_limit = LEAST(plots_limit, 1),
            plants_limit = LEAST(plants_limit, 10)
        WHERE subscription_tier = 'free'
        """
    )
