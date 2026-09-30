"""document language code

Revision ID: d4e1a8c90b17
Revises: b7d2e9a41c08
Create Date: 2026-09-29 22:40:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e1a8c90b17"
down_revision: Union[str, None] = "b7d2e9a41c08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("candidate_documents", sa.Column("language_code", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("candidate_documents", "language_code")
