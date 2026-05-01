"""Add grid_data JSONB column to plots table.

Revision ID: 002_garden_grid
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_garden_grid"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plots",
        sa.Column(
            "grid_data",
            postgresql.JSONB(),
            nullable=True,
            comment="Garden grid layout: {cols, rows, cells: [{col, row, plant_type, ...}]}",
        ),
    )


def downgrade() -> None:
    op.drop_column("plots", "grid_data")
