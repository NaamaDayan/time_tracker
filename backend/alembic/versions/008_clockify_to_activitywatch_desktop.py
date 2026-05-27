"""Replace clockify source with activitywatch_desktop

Revision ID: 008
Revises: 007
Create Date: 2026-05-26

"""

from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE source_accounts
        SET source = 'activitywatch_desktop',
            display_name = 'ActivityWatch Desktop'
        WHERE source = 'clockify'
        """
    )
    op.execute(
        """
        UPDATE raw_events
        SET source = 'activitywatch_desktop'
        WHERE source = 'clockify'
        """
    )
    op.execute(
        """
        UPDATE activity_segments
        SET source = 'activitywatch_desktop'
        WHERE source = 'clockify'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE source_accounts
        SET source = 'clockify',
            display_name = 'Clockify'
        WHERE source = 'activitywatch_desktop'
        """
    )
    op.execute(
        """
        UPDATE raw_events
        SET source = 'clockify'
        WHERE source = 'activitywatch_desktop'
        """
    )
    op.execute(
        """
        UPDATE activity_segments
        SET source = 'clockify'
        WHERE source = 'activitywatch_desktop'
        """
    )
