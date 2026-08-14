"""add post_feedback for hide and not-interested

Revision ID: 009
Revises: 008
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "post_feedback",
        sa.Column("viewer_id", sa.UUID(), nullable=False),
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["viewer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("viewer_id", "post_id"),
        sa.UniqueConstraint("viewer_id", "post_id", name="uq_post_feedback_pair"),
    )
    op.create_index("ix_post_feedback_post_id", "post_feedback", ["post_id"])


def downgrade() -> None:
    op.drop_index("ix_post_feedback_post_id", table_name="post_feedback")
    op.drop_table("post_feedback")
