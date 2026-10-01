"""Each hiring request names the company contact its shortlist goes to.

Before this, every company's shortlist went to one configured address, so a recruiter could not check that
Company A's candidates were going to Company A.

Revision ID: a2d4f6b8c013
Revises: f1b3d5a7c920
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2d4f6b8c013"
down_revision: Union[str, None] = "f1b3d5a7c920"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hiring_requests", sa.Column("contact_email", sa.String(320), nullable=True))


def downgrade() -> None:
    op.drop_column("hiring_requests", "contact_email")
