"""Add pos_x, pos_y, width, height to plots table.

Revision ID: 003_plot_position
"""
from alembic import op
import sqlalchemy as sa

revision = "003_plot_position"
down_revision = "002_garden_grid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plots", sa.Column("pos_x", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("plots", sa.Column("pos_y", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("plots", sa.Column("width", sa.Integer(), nullable=False, server_default="200"))
    op.add_column("plots", sa.Column("height", sa.Integer(), nullable=False, server_default="150"))


def downgrade() -> None:
    op.drop_column("plots", "height")
    op.drop_column("plots", "width")
    op.drop_column("plots", "pos_y")
    op.drop_column("plots", "pos_x")