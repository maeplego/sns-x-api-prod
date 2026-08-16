"""add privacy_version on users

Revision ID: 014
Revises: 013
Create Date: 2026-08-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("privacy_version", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "privacy_version")
