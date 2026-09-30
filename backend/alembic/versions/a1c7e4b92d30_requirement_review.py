"""requirement review status

Revision ID: a1c7e4b92d30
Revises: f3a9c2d81e06
Create Date: 2026-09-29 23:05:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c7e4b92d30"
down_revision: Union[str, None] = "f3a9c2d81e06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "request_requirements",
        sa.Column("review_status", sa.String(length=32), server_default="proposed", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("request_requirements", "review_status")
