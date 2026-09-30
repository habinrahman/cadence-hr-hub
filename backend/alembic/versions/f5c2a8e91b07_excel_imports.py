"""excel import batches

Revision ID: f5c2a8e91b07
Revises: e2a9c7b18d44
Create Date: 2026-09-29 23:58:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f5c2a8e91b07"
down_revision: Union[str, None] = "e2a9c7b18d44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "excel_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("sheet_count", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("valid_count", sa.Integer(), nullable=False),
        sa.Column("invalid_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("relationship_count", sa.Integer(), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("ignored_column_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_excel_imports_actor_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_excel_imports"),
    )
    op.create_table(
        "excel_import_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("error_codes", postgresql.JSONB(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=True),
        sa.Column("relationship", sa.String(length=32), nullable=True),
        sa.Column("duplicate_of_row", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], name="fk_excel_import_rows_candidate_id_candidates"),
        sa.ForeignKeyConstraint(["import_id"], ["excel_imports.id"], name="fk_excel_import_rows_import_id_excel_imports"),
        sa.PrimaryKeyConstraint("id", name="pk_excel_import_rows"),
    )


def downgrade() -> None:
    op.drop_table("excel_import_rows")
    op.drop_table("excel_imports")
