"""Reject TRUNCATE on audit_events. UPDATE and DELETE were already rejected row by row.

A statement-level trigger stops TRUNCATE from any ordinary session, including the application's.
It cannot stop the table owner or a superuser who first disables or drops the trigger; that needs a
separate, non-owner application role in production.

Revision ID: d1e7f3a92c40
Revises: a9d3c5e17b42
Create Date: 2026-09-30 18:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d1e7f3a92c40"
down_revision: Union[str, None] = "a9d3c5e17b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TRIGGER audit_events_no_truncate
        BEFORE TRUNCATE ON audit_events
        FOR EACH STATEMENT
        EXECUTE FUNCTION reject_audit_event_mutation()
        """
    )
    op.execute("REVOKE TRUNCATE ON audit_events FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_truncate ON audit_events")
