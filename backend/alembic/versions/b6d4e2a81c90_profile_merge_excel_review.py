"""Profile merge pointer and Excel relationship reviews.

Revision ID: b6d4e2a81c90
Revises: f5c2a8e91b07
Create Date: 2026-09-30 00:45:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6d4e2a81c90"
down_revision: Union[str, None] = "f5c2a8e91b07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("merged_into_id", sa.Uuid(), nullable=True))
    op.add_column("candidates", sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_candidates_merged_into_id_candidates",
        "candidates",
        "candidates",
        ["merged_into_id"],
        ["id"],
    )
    op.add_column("excel_import_rows", sa.Column("proposed_name", sa.String(length=200), nullable=True))
    op.add_column("excel_import_rows", sa.Column("proposed_email", sa.String(length=320), nullable=True))
    op.add_column("excel_import_rows", sa.Column("proposed_phone", sa.String(length=32), nullable=True))
    op.add_column("duplicate_reviews", sa.Column("excel_import_row_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_duplicate_reviews_excel_import_row_id_excel_import_rows",
        "duplicate_reviews",
        "excel_import_rows",
        ["excel_import_row_id"],
        ["id"],
    )
    op.alter_column("duplicate_reviews", "document_id", existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint(
        "ck_duplicate_reviews_subject",
        "duplicate_reviews",
        "document_id IS NOT NULL OR excel_import_row_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_duplicate_reviews_subject", "duplicate_reviews", type_="check")
    op.execute("DELETE FROM duplicate_reviews WHERE document_id IS NULL")
    op.alter_column("duplicate_reviews", "document_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_constraint(
        "fk_duplicate_reviews_excel_import_row_id_excel_import_rows",
        "duplicate_reviews",
        type_="foreignkey",
    )
    op.drop_column("duplicate_reviews", "excel_import_row_id")
    op.drop_column("excel_import_rows", "proposed_phone")
    op.drop_column("excel_import_rows", "proposed_email")
    op.drop_column("excel_import_rows", "proposed_name")
    op.drop_constraint("fk_candidates_merged_into_id_candidates", "candidates", type_="foreignkey")
    op.drop_column("candidates", "merged_at")
    op.drop_column("candidates", "merged_into_id")
