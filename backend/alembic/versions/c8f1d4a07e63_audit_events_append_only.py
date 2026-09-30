"""Reject updates and deletes on audit_events.

Revision ID: c8f1d4a07e63
Revises: b6d4e2a81c90
Create Date: 2026-09-30 05:50:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c8f1d4a07e63"
down_revision: Union[str, None] = "b6d4e2a81c90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events are append-only'
                USING ERRCODE = '42501';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW
        EXECUTE FUNCTION reject_audit_event_mutation()
        """
    )
    op.execute("REVOKE UPDATE, DELETE ON audit_events FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS reject_audit_event_mutation()")
