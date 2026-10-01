"""One approval decision per shortlisted candidate and decision.

approve_share is serialised with a row lock; this index is the database backstop. Duplicate approvals recorded by
double clicks before the lock existed are kept but marked superseded, so the unique index can be built without
deleting any decision.

Revision ID: b3c5e7a9d124
Revises: a2d4f6b8c013
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b3c5e7a9d124"
down_revision: Union[str, None] = "a2d4f6b8c013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE approval_decisions SET decision = 'superseded'
        WHERE decision = 'approved' AND id NOT IN (
            SELECT DISTINCT ON (subject_type, subject_id) id FROM approval_decisions
            WHERE decision = 'approved' ORDER BY subject_type, subject_id, created_at, id
        )
        """
    )
    op.create_index(
        "uq_approval_decisions_one_approval",
        "approval_decisions",
        ["subject_type", "subject_id"],
        unique=True,
        postgresql_where="decision = 'approved'",
    )


def downgrade() -> None:
    op.drop_index("uq_approval_decisions_one_approval", table_name="approval_decisions")
