"""sharing delivery fields

Revision ID: c3f8a1d04e72
Revises: a1c7e4b92d30
Create Date: 2026-09-29 23:20:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3f8a1d04e72"
down_revision: Union[str, None] = "a1c7e4b92d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sharing_records", sa.Column("request_id", sa.Uuid(), nullable=True))
    op.add_column("sharing_records", sa.Column("recipient", sa.String(length=320), nullable=True))
    op.add_column(
        "sharing_records",
        sa.Column("status", sa.String(length=32), server_default="sent", nullable=False),
    )
    op.add_column("sharing_records", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_sharing_records_request_id_hiring_requests"),
        "sharing_records",
        "hiring_requests",
        ["request_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_sharing_records_request_id_hiring_requests"),
        "sharing_records",
        type_="foreignkey",
    )
    op.drop_column("sharing_records", "sent_at")
    op.drop_column("sharing_records", "status")
    op.drop_column("sharing_records", "recipient")
    op.drop_column("sharing_records", "request_id")
