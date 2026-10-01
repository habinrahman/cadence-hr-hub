"""A sourced candidate can be recorded before a CV exists (a LinkedIn lead, a referral).

Revision ID: f1b3d5a7c920
Revises: e7a2c4f19b60
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1b3d5a7c920"
down_revision: Union[str, None] = "e7a2c4f19b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("candidate_sources", "document_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM candidate_sources WHERE document_id IS NULL")
    op.alter_column("candidate_sources", "document_id", existing_type=sa.Uuid(), nullable=False)
