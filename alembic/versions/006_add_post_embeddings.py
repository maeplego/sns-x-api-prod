"""add post_embeddings with pgvector

Revision ID: 006
Revises: 005
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "post_embeddings",
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False, server_default="hash-v1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("post_id"),
    )
    op.execute(
        """
        CREATE INDEX ix_post_embeddings_hnsw
        ON post_embeddings
        USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_post_embeddings_hnsw", table_name="post_embeddings")
    op.drop_table("post_embeddings")
