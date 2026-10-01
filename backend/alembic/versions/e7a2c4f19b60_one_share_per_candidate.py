"""One draft shortlist per request, one send per shortlisted candidate.

The service layer serialises these decisions with row locks. These indexes are the backstop: if two requests ever
slip past the lock, the database refuses the second row instead of storing a second shortlist or a second send.

Revision ID: e7a2c4f19b60
Revises: d1e7f3a92c40
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e7a2c4f19b60"
down_revision: Union[str, None] = "d1e7f3a92c40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Repair before constraining. A database that already holds duplicates from double clicks keeps every row:
    # later draft shortlists for a request are marked superseded, and later sends of the same shortlisted candidate
    # are marked sent_duplicate (the email did go out; it is no longer counted as a second share).
    op.execute(
        """
        UPDATE shortlists SET status = 'superseded'
        WHERE status = 'draft' AND id NOT IN (
            SELECT DISTINCT ON (request_id) id FROM shortlists
            WHERE status = 'draft' ORDER BY request_id, created_at, id
        )
        """
    )
    op.execute(
        """
        UPDATE sharing_records SET status = 'sent_duplicate'
        WHERE status = 'sent' AND id NOT IN (
            SELECT DISTINCT ON (shortlist_id, candidate_id) id FROM sharing_records
            WHERE status = 'sent' ORDER BY shortlist_id, candidate_id, created_at, id
        )
        """
    )
    op.create_index(
        "uq_shortlists_one_draft_per_request",
        "shortlists",
        ["request_id"],
        unique=True,
        postgresql_where="status = 'draft'",
    )
    op.create_index(
        "uq_sharing_records_one_send",
        "sharing_records",
        ["shortlist_id", "candidate_id"],
        unique=True,
        postgresql_where="status = 'sent'",
    )


def downgrade() -> None:
    op.drop_index("uq_sharing_records_one_send", table_name="sharing_records")
    op.drop_index("uq_shortlists_one_draft_per_request", table_name="shortlists")
