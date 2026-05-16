"""seed all activity types

Revision ID: 002
Revises: 001
Create Date: 2026-05-16

"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO activity_types (slug, label, color) VALUES
        ('sleep', 'Sleep', '#6366f1'),
        ('sport', 'Sport', '#22c55e'),
        ('read', 'Read', '#f59e0b'),
        ('fun', 'Fun', '#ec4899'),
        ('consuming', 'Consuming', '#a855f7'),
        ('transport', 'Transport', '#14b8a6'),
        ('communication', 'Communication', '#0ea5e9'),
        ('eat', 'Eat', '#f97316')
        ON CONFLICT (slug) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM activity_types WHERE slug IN (
            'sleep', 'sport', 'read', 'fun', 'consuming',
            'transport', 'communication', 'eat'
        )
        """
    )
