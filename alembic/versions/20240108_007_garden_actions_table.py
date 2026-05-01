"""Move garden actions from plots.grid_data JSONB into a table.

Revision ID: 007_garden_actions_table
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007_garden_actions_table"
down_revision = "006_plot_soil_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("garden_actions"):
        op.create_table(
            "garden_actions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("plot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plots.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("action_type", sa.String(40), nullable=False),
            sa.Column("plant_type", sa.String(100), nullable=True),
            sa.Column("variety", sa.String(100), nullable=True),
            sa.Column("cell_col", sa.Integer(), nullable=True),
            sa.Column("cell_row", sa.Integer(), nullable=True),
            sa.Column("amount", sa.String(100), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("task_title", sa.Text(), nullable=True),
            sa.Column("scope", sa.String(20), nullable=False, server_default="single"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("garden_actions")}
    if "ix_garden_actions_created_at" not in indexes:
        op.create_index("ix_garden_actions_created_at", "garden_actions", ["created_at"])
    if "ix_garden_actions_plot_created" not in indexes:
        op.execute(
            "CREATE INDEX ix_garden_actions_plot_created "
            "ON garden_actions (plot_id, created_at DESC)"
        )
    if "ix_garden_actions_lookup" not in indexes:
        op.create_index(
            "ix_garden_actions_lookup",
            "garden_actions",
            ["plot_id", "action_type", "plant_type", "variety", "cell_col", "cell_row"],
        )

    op.execute(
        """
        INSERT INTO garden_actions (
            id, plot_id, user_id, action_type, plant_type, variety, cell_col,
            cell_row, amount, notes, task_title, scope, created_at
        )
        SELECT
            COALESCE((action->>'id')::uuid, uuid_generate_v4()),
            p.id,
            p.user_id,
            COALESCE(action->>'action_type', 'general'),
            action->>'plant_type',
            action->>'variety',
            NULLIF(action->>'cell_col', '')::integer,
            NULLIF(action->>'cell_row', '')::integer,
            action->>'amount',
            action->>'notes',
            action->>'task_title',
            COALESCE(action->>'scope', 'single'),
            COALESCE(NULLIF(action->>'created_at', '')::timestamptz, now())
        FROM plots p
        CROSS JOIN LATERAL jsonb_array_elements(COALESCE(p.grid_data->'actions', '[]'::jsonb)) AS action
        WHERE p.grid_data ? 'actions'
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute("UPDATE plots SET grid_data = grid_data - 'actions' WHERE grid_data ? 'actions'")


def downgrade() -> None:
    op.drop_index("ix_garden_actions_lookup", table_name="garden_actions")
    op.drop_index("ix_garden_actions_plot_created", table_name="garden_actions")
    op.drop_index("ix_garden_actions_created_at", table_name="garden_actions")
    op.drop_table("garden_actions")
