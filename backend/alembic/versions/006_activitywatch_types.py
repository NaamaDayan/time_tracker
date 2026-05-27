"""add phone_usage and music_podcast activity types; activitywatch source account

Revision ID: 006
Revises: 005
Create Date: 2026-05-20

"""

from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO activity_types (slug, label, color) VALUES
        ('phone_usage', 'Phone Usage', '#64748b'),
        ('music_podcast', 'Music / Podcast', '#84cc16')
        ON CONFLICT (slug) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO source_accounts (source, display_name, config_json, is_active)
        VALUES ('activitywatch', 'Activity Watch', '{}', false)
        ON CONFLICT (source) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM source_accounts WHERE source = 'activitywatch'")
    op.execute(
        """
        DELETE FROM activity_types WHERE slug IN ('phone_usage', 'music_podcast')
        """
    )
