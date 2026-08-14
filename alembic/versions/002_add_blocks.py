"""add blocks table

Revision ID: 002
Revises: 001
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "blocks",
        sa.Column("blocker_id", sa.UUID(), nullable=False),
        sa.Column("blocked_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["blocked_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["blocker_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("blocker_id", "blocked_id"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_blocks_pair"),
    )


def downgrade() -> None:
    op.drop_table("blocks")
