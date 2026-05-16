"""seed google calendar source account

Revision ID: 003
Revises: 002
Create Date: 2026-05-16

"""

from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO source_accounts (source, display_name, config_json, is_active)
        VALUES ('google_calendar', 'Google Calendar', '{}', true)
        ON CONFLICT (source) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM source_accounts WHERE source = 'google_calendar'")
