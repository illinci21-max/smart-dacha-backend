"""Add SAT delta tracking date to plants.

Revision ID: 017_plant_sat_last_updated
Revises: 016_plot_elevation
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa


revision = "017_plant_sat_last_updated"
down_revision = "016_plot_elevation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plants", sa.Column("sat_last_updated_at", sa.Date(), nullable=True))
    op.execute("""
        UPDATE plants
        SET sat_last_updated_at = CURRENT_DATE
        WHERE sat_accumulated > 0
          AND sat_last_updated_at IS NULL
    """)


def downgrade() -> None:
    op.drop_column("plants", "sat_last_updated_at")
