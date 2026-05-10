"""Add forum topic and reply tables.

Revision ID: 023_forum_tables
Revises: 022_user_firebase_token
"""
from alembic import op


revision = "023_forum_tables"
down_revision = "022_user_firebase_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS forum_topics (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            title VARCHAR(200) NOT NULL,
            body TEXT NOT NULL,
            tag VARCHAR(50) NOT NULL DEFAULT 'Загальне',
            views_count INTEGER NOT NULL DEFAULT 0,
            replies_count INTEGER NOT NULL DEFAULT 0,
            is_pinned BOOLEAN NOT NULL DEFAULT false,
            is_deleted BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS forum_replies (
            id UUID PRIMARY KEY,
            topic_id UUID NOT NULL REFERENCES forum_topics(id),
            user_id UUID NOT NULL REFERENCES users(id),
            body TEXT NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_forum_topics_deleted_pinned_created "
        "ON forum_topics (is_deleted, is_pinned DESC, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_forum_topics_deleted_tag_created "
        "ON forum_topics (is_deleted, tag, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_forum_replies_topic_deleted_created "
        "ON forum_replies (topic_id, is_deleted, created_at ASC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_forum_replies_topic_deleted_created")
    op.execute("DROP INDEX IF EXISTS ix_forum_topics_deleted_tag_created")
    op.execute("DROP INDEX IF EXISTS ix_forum_topics_deleted_pinned_created")
    op.drop_table("forum_replies")
    op.drop_table("forum_topics")
