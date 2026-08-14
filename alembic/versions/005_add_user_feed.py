"""add user_feed fan-out cache

Revision ID: 005
Revises: 004
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_feed",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id", "post_id"),
        sa.UniqueConstraint("user_id", "post_id", name="uq_user_feed_pair"),
    )
    op.create_index("ix_user_feed_author_id", "user_feed", ["author_id"])
    op.create_index("ix_user_feed_created_at", "user_feed", ["created_at"])
    op.create_index("ix_user_feed_user_created", "user_feed", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_feed_user_created", table_name="user_feed")
    op.drop_index("ix_user_feed_created_at", table_name="user_feed")
    op.drop_index("ix_user_feed_author_id", table_name="user_feed")
    op.drop_table("user_feed")
