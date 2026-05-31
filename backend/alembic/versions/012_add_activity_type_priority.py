"""add activity_type_priorities table

Revision ID: 012
Revises: 011
Create Date: 2026-05-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_type_priorities",
        sa.Column(
            "activity_type_slug",
            sa.String(64),
            sa.ForeignKey("activity_types.slug"),
            primary_key=True,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("activity_type_priorities")
