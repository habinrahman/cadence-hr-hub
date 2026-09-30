"""relationship evidence and company send

Revision ID: e4c8a1b27f30
Revises: c52aff4d6b1a
Create Date: 2026-09-29 20:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e4c8a1b27f30"
down_revision: Union[str, None] = "c52aff4d6b1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("duplicate_reviews", sa.Column("confidence", sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column("duplicate_reviews", sa.Column("likely_relationship", sa.String(length=32), nullable=True))
    op.add_column("duplicate_reviews", sa.Column("recommended_action", sa.String(length=64), nullable=True))
    op.add_column(
        "duplicate_reviews",
        sa.Column("offered_actions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.alter_column("sharing_records", "shortlist_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    op.alter_column("sharing_records", "shortlist_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("duplicate_reviews", "offered_actions")
    op.drop_column("duplicate_reviews", "recommended_action")
    op.drop_column("duplicate_reviews", "likely_relationship")
    op.drop_column("duplicate_reviews", "confidence")
