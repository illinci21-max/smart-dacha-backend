"""Add finance_transactions table (full schema).

Revision ID: 004_finance
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004_finance"
down_revision = "003_plot_position"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("type", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("plot", sa.String(100), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("type IN ('income', 'expense')", name="ck_finance_type"),
        sa.CheckConstraint("amount > 0", name="ck_finance_amount_positive"),
    )


def downgrade() -> None:
    op.drop_table("finance_transactions")