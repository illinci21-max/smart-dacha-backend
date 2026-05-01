"""Add enriched weather fields for agro analysis.

Revision ID: 005_weather_enrichment
"""
from alembic import op
import sqlalchemy as sa

revision = "005_weather_enrichment"
down_revision = "004_finance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("weather_daily_cache", sa.Column("humidity_avg", sa.Numeric(5, 2), nullable=True))
    op.add_column("weather_daily_cache", sa.Column("humidity_max", sa.Numeric(5, 2), nullable=True))
    op.add_column("weather_daily_cache", sa.Column("cloud_cover", sa.Numeric(5, 2), nullable=True))
    op.add_column("weather_daily_cache", sa.Column("has_dew", sa.Boolean(), nullable=True))
    op.add_column("weather_daily_cache", sa.Column("is_fog", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("weather_daily_cache", "is_fog")
    op.drop_column("weather_daily_cache", "has_dew")
    op.drop_column("weather_daily_cache", "cloud_cover")
    op.drop_column("weather_daily_cache", "humidity_max")
    op.drop_column("weather_daily_cache", "humidity_avg")