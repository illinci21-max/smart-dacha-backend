"""Add soil_type to plots.

Revision ID: 006_plot_soil_type
"""
from alembic import op
import sqlalchemy as sa

revision = "006_plot_soil_type"
down_revision = "005_weather_enrichment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plots", sa.Column("soil_type", sa.String(30), nullable=False, server_default="loam"))


def downgrade() -> None:
    op.drop_column("plots", "soil_type")
