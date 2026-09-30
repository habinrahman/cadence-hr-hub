"""original and normalized page text

Revision ID: b7d2e9a41c08
Revises: e4c8a1b27f30
Create Date: 2026-09-29 22:20:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2e9a41c08"
down_revision: Union[str, None] = "e4c8a1b27f30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["candidate_documents.id"],
            name=op.f("fk_document_pages_document_id_candidate_documents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_pages")),
        sa.UniqueConstraint("document_id", "page_number", name="uq_document_pages_number"),
    )


def downgrade() -> None:
    op.drop_table("document_pages")
