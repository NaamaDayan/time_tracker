"""nullable activity_segments.ended_at; location source accounts

Revision ID: 007
Revises: 006
Create Date: 2026-05-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "activity_segments",
        "ended_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.execute(
        """
        INSERT INTO source_accounts (source, display_name, config_json, is_active)
        VALUES
            ('geofence', 'Geofence zones', '{}', true),
            ('dawarich', 'Dawarich visits', '{}', false)
        ON CONFLICT (source) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM source_accounts WHERE source IN ('geofence', 'dawarich')")
    op.execute(
        """
        UPDATE activity_segments SET ended_at = started_at + interval '1 second'
        WHERE ended_at IS NULL
        """
    )
    op.alter_column(
        "activity_segments",
        "ended_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
