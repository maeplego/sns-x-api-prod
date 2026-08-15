"""add quote/repost columns and repost_count

Revision ID: 010
Revises: 009
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("quote_of_id", sa.UUID(), nullable=True))
    op.add_column("posts", sa.Column("repost_of_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_posts_quote_of_id", "posts", "posts", ["quote_of_id"], ["id"])
    op.create_foreign_key("fk_posts_repost_of_id", "posts", "posts", ["repost_of_id"], ["id"])
    op.create_index("ix_posts_quote_of_id", "posts", ["quote_of_id"])
    op.create_index("ix_posts_repost_of_id", "posts", ["repost_of_id"])
    op.add_column(
        "post_engagement",
        sa.Column("repost_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("post_engagement", "repost_count")
    op.drop_index("ix_posts_repost_of_id", table_name="posts")
    op.drop_index("ix_posts_quote_of_id", table_name="posts")
    op.drop_constraint("fk_posts_repost_of_id", "posts", type_="foreignkey")
    op.drop_constraint("fk_posts_quote_of_id", "posts", type_="foreignkey")
    op.drop_column("posts", "repost_of_id")
    op.drop_column("posts", "quote_of_id")
