"""seed samsung_health source account placeholder

Revision ID: 005
Revises: 004
Create Date: 2026-05-17

"""

from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO source_accounts (source, display_name, config_json, is_active)
        VALUES ('samsung_health', 'Samsung Health', '{}', false)
        ON CONFLICT (source) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM source_accounts WHERE source = 'samsung_health'")
