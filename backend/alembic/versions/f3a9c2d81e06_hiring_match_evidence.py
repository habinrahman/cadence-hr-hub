"""hiring request evidence and shortlist review fields

Revision ID: f3a9c2d81e06
Revises: d4e1a8c90b17
Create Date: 2026-09-29 22:50:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a9c2d81e06"
down_revision: Union[str, None] = "d4e1a8c90b17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("request_notes", sa.Column("kind", sa.String(length=32), server_default="note", nullable=False))
    op.add_column("request_requirements", sa.Column("source_quote", sa.Text(), nullable=True))
    op.add_column("candidate_matches", sa.Column("explanation", sa.String(length=500), nullable=True))
    op.add_column("candidate_matches", sa.Column("processing_version", sa.Integer(), nullable=True))
    op.add_column("match_requirement_results", sa.Column("evidence_quote", sa.String(length=160), nullable=True))
    op.add_column("match_requirement_results", sa.Column("retrieval", sa.String(length=32), nullable=True))
    op.add_column("shortlist_candidates", sa.Column("added_by_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "shortlist_candidates",
        sa.Column("review_state", sa.String(length=32), server_default="shortlisted", nullable=False),
    )
    op.add_column("shortlist_candidates", sa.Column("note", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_shortlist_candidates_added_by_user_id_users"),
        "shortlist_candidates",
        "users",
        ["added_by_user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_shortlist_candidates_added_by_user_id_users"), "shortlist_candidates", type_="foreignkey")
    op.drop_column("shortlist_candidates", "note")
    op.drop_column("shortlist_candidates", "review_state")
    op.drop_column("shortlist_candidates", "added_by_user_id")
    op.drop_column("match_requirement_results", "retrieval")
    op.drop_column("match_requirement_results", "evidence_quote")
    op.drop_column("candidate_matches", "processing_version")
    op.drop_column("candidate_matches", "explanation")
    op.drop_column("request_requirements", "source_quote")
    op.drop_column("request_notes", "kind")
