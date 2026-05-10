"""Add weather_zones.created_at.

Revision ID: 025_weather_zones_created_at
Revises: 024_unlock_free_tier_limits
"""
from alembic import op
import sqlalchemy as sa

revision = "025_weather_zones_created_at"
down_revision = "024_unlock_free_tier_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "weather_zones",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("weather_zones", "created_at")
