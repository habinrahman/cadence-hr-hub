"""problem report context and engineer notes

Revision ID: e2a9c7b18d44
Revises: d8b1e6a04c55
Create Date: 2026-09-29 23:55:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e2a9c7b18d44"
down_revision: Union[str, None] = "d8b1e6a04c55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "problem_reports",
        sa.Column("category", sa.String(length=32), server_default="other", nullable=False),
    )
    op.add_column(
        "problem_reports",
        sa.Column("detail", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "problem_reports",
        sa.Column("context", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.add_column("problem_reports", sa.Column("engineering_note", sa.Text(), nullable=True))
    op.add_column(
        "problem_reports",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.alter_column("problem_reports", "entity_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column(
        "problem_reports",
        "entity_type",
        existing_type=sa.String(length=64),
        server_default="none",
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column("problem_reports", "entity_type", existing_type=sa.String(length=64), server_default=None)
    op.execute("DELETE FROM problem_reports WHERE entity_id IS NULL")
    op.alter_column("problem_reports", "entity_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("problem_reports", "updated_at")
    op.drop_column("problem_reports", "engineering_note")
    op.drop_column("problem_reports", "context")
    op.drop_column("problem_reports", "detail")
    op.drop_column("problem_reports", "category")
