"""Add plot elevation for FAO-56 ET0.

Revision ID: 016_plot_elevation
Revises: 015_garden_observations
"""

from alembic import op
import sqlalchemy as sa


revision = "016_plot_elevation"
down_revision = "015_garden_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("plots")}
    if "elevation_m" not in columns:
        op.add_column("plots", sa.Column("elevation_m", sa.Numeric(6, 1), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("plots")}
    if "elevation_m" in columns:
        op.drop_column("plots", "elevation_m")
