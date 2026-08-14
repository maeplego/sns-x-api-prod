"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("handle", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "status",
            sa.Enum("active", "suspended", name="user_status", native_enum=False),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("handle"),
    )
    op.create_index("ix_users_handle", "users", ["handle"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "posts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "visibility",
            sa.Enum("public", "followers_only", name="post_visibility", native_enum=False),
            nullable=False,
            server_default="public",
        ),
        sa.Column(
            "status",
            sa.Enum("published", "processing", "failed", name="post_status", native_enum=False),
            nullable=False,
            server_default="published",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_posts_author_id", "posts", ["author_id"])
    op.create_index("ix_posts_created_at", "posts", ["created_at"])

    op.create_table(
        "follows",
        sa.Column("follower_id", sa.UUID(), nullable=False),
        sa.Column("followee_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["followee_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["follower_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("follower_id", "followee_id"),
        sa.UniqueConstraint("follower_id", "followee_id", name="uq_follows_pair"),
    )


def downgrade() -> None:
    op.drop_table("follows")
    op.drop_index("ix_posts_created_at", table_name="posts")
    op.drop_index("ix_posts_author_id", table_name="posts")
    op.drop_table("posts")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_handle", table_name="users")
    op.drop_table("users")
