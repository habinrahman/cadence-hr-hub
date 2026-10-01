"""request processing state

Revision ID: a9d3c5e17b42
Revises: c8f1d4a07e63
Create Date: 2026-09-30 15:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9d3c5e17b42"
down_revision: Union[str, None] = "c8f1d4a07e63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hiring_requests", sa.Column("pool_opened_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hiring_requests", sa.Column("last_match_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hiring_requests", sa.Column("pool_stale", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("hiring_requests", sa.Column("requested_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("hiring_requests", "requested_count")
    op.drop_column("hiring_requests", "pool_stale")
    op.drop_column("hiring_requests", "last_match_completed_at")
    op.drop_column("hiring_requests", "pool_opened_at")
