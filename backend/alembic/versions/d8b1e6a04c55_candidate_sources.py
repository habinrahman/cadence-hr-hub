"""sourced candidate records

Revision ID: d8b1e6a04c55
Revises: c3f8a1d04e72
Create Date: 2026-09-29 23:40:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8b1e6a04c55"
down_revision: Union[str, None] = "c3f8a1d04e72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_reference", sa.String(length=300), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], name=op.f("fk_candidate_sources_candidate_id_candidates")),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], name=op.f("fk_candidate_sources_created_by_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["candidate_documents.id"], name=op.f("fk_candidate_sources_document_id_candidate_documents")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_sources")),
        sa.UniqueConstraint("document_id", name=op.f("uq_candidate_sources_document_id")),
    )


def downgrade() -> None:
    op.drop_table("candidate_sources")
