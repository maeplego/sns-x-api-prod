"""add safety labels and user cred_score

Revision ID: 011
Revises: 010
Create Date: 2026-08-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("cred_score", sa.Float(), nullable=False, server_default="50"),
    )
    op.create_table(
        "safety_labels",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("target_type", "target_id", "label", name="uq_safety_labels_target_label"),
    )
    op.create_index("ix_safety_labels_target_id", "safety_labels", ["target_id"])
    op.create_index("ix_safety_labels_label", "safety_labels", ["label"])
    op.create_index("ix_safety_labels_created_at", "safety_labels", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_safety_labels_created_at", table_name="safety_labels")
    op.drop_index("ix_safety_labels_label", table_name="safety_labels")
    op.drop_index("ix_safety_labels_target_id", table_name="safety_labels")
    op.drop_table("safety_labels")
    op.drop_column("users", "cred_score")
