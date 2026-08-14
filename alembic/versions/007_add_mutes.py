"""add mutes and muted_keywords

Revision ID: 007
Revises: 006
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mutes",
        sa.Column("muter_id", sa.UUID(), nullable=False),
        sa.Column("muted_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["muted_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["muter_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("muter_id", "muted_id"),
        sa.UniqueConstraint("muter_id", "muted_id", name="uq_mutes_pair"),
    )
    op.create_table(
        "muted_keywords",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("keyword", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "keyword", name="uq_muted_keywords_user_keyword"),
    )
    op.create_index("ix_muted_keywords_user_id", "muted_keywords", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_muted_keywords_user_id", table_name="muted_keywords")
    op.drop_table("muted_keywords")
    op.drop_table("mutes")
