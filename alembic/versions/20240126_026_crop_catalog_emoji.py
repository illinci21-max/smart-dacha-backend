"""Add crop_catalog.emoji.

Revision ID: 026_crop_catalog_emoji
Revises: 025_weather_zones_created_at
"""
from alembic import op
import sqlalchemy as sa

revision = "026_crop_catalog_emoji"
down_revision = "025_weather_zones_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crop_catalog", sa.Column("emoji", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("crop_catalog", "emoji")
