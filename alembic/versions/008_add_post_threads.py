"""add post parent_id and root_id for threads

Revision ID: 008
Revises: 007
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("parent_id", sa.UUID(), nullable=True))
    op.add_column("posts", sa.Column("root_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_posts_parent_id", "posts", "posts", ["parent_id"], ["id"])
    op.create_foreign_key("fk_posts_root_id", "posts", "posts", ["root_id"], ["id"])
    op.create_index("ix_posts_parent_id", "posts", ["parent_id"])
    op.create_index("ix_posts_root_id", "posts", ["root_id"])


def downgrade() -> None:
    op.drop_index("ix_posts_root_id", table_name="posts")
    op.drop_index("ix_posts_parent_id", table_name="posts")
    op.drop_constraint("fk_posts_root_id", "posts", type_="foreignkey")
    op.drop_constraint("fk_posts_parent_id", "posts", type_="foreignkey")
    op.drop_column("posts", "root_id")
    op.drop_column("posts", "parent_id")
