"""Add composite indexes for hot application queries.

Revision ID: 021_composite_indexes
Revises: 020_observation_species_filter
"""
from alembic import op


revision = "021_composite_indexes"
down_revision = "020_observation_species_filter"
branch_labels = None
depends_on = None


_INDEXES = (
    (
        "ix_plots_user_deleted_created",
        "plots",
        "CREATE INDEX IF NOT EXISTS ix_plots_user_deleted_created "
        "ON plots (user_id, is_deleted, created_at DESC)",
    ),
    (
        "ix_plants_plot_deleted",
        "plants",
        "CREATE INDEX IF NOT EXISTS ix_plants_plot_deleted "
        "ON plants (plot_id, is_deleted)",
    ),
    (
        "ix_plants_user_deleted",
        "plants",
        "CREATE INDEX IF NOT EXISTS ix_plants_user_deleted "
        "ON plants (user_id, is_deleted)",
    ),
    (
        "ix_finance_user_date_desc",
        "finance_transactions",
        "CREATE INDEX IF NOT EXISTS ix_finance_user_date_desc "
        "ON finance_transactions (user_id, date DESC)",
    ),
    (
        "ix_finance_user_type",
        "finance_transactions",
        "CREATE INDEX IF NOT EXISTS ix_finance_user_type "
        "ON finance_transactions (user_id, type)",
    ),
    (
        "ix_care_journal_plant_deleted_performed",
        "care_journal",
        "CREATE INDEX IF NOT EXISTS ix_care_journal_plant_deleted_performed "
        "ON care_journal (plant_id, is_deleted, performed_at DESC)",
    ),
    (
        "ix_care_journal_user_updated",
        "care_journal",
        "CREATE INDEX IF NOT EXISTS ix_care_journal_user_updated "
        "ON care_journal (user_id, updated_at)",
    ),
)


_OPTIONAL_INDEXES = (
    (
        "ix_forum_topics_deleted_pinned_created",
        "forum_topics",
        "CREATE INDEX IF NOT EXISTS ix_forum_topics_deleted_pinned_created "
        "ON forum_topics (is_deleted, is_pinned DESC, created_at DESC)",
    ),
    (
        "ix_forum_topics_deleted_tag_created",
        "forum_topics",
        "CREATE INDEX IF NOT EXISTS ix_forum_topics_deleted_tag_created "
        "ON forum_topics (is_deleted, tag, created_at DESC)",
    ),
    (
        "ix_forum_replies_topic_deleted_created",
        "forum_replies",
        "CREATE INDEX IF NOT EXISTS ix_forum_replies_topic_deleted_created "
        "ON forum_replies (topic_id, is_deleted, created_at ASC)",
    ),
)


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return bool(bind.exec_driver_sql("SELECT to_regclass(%s)", (table_name,)).scalar())


def upgrade() -> None:
    for _, _, statement in _INDEXES:
        op.execute(statement)

    # Forum tables are present in some deployments but are not part of the
    # stable migration chain yet. Create their hot-path indexes only when the
    # tables already exist.
    for _, table_name, statement in _OPTIONAL_INDEXES:
        if _table_exists(table_name):
            op.execute(statement)


def downgrade() -> None:
    for index_name, table_name, _ in reversed(_OPTIONAL_INDEXES + _INDEXES):
        if _table_exists(table_name):
            op.execute(f"DROP INDEX IF EXISTS {index_name}")
