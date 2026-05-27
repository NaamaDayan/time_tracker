"""add activity_rule_configs table

Revision ID: 010
Revises: 009
Create Date: 2026-05-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_rule_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "activity_type_slug",
            sa.String(64),
            sa.ForeignKey("activity_types.slug"),
            nullable=False,
            unique=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("min_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("merge_gap_minutes", sa.Integer(), nullable=False),
        sa.Column("boost_signals", JSONB(), nullable=False, server_default="{}"),
        sa.Column("custom_params", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.execute(
        """
        INSERT INTO activity_types (slug, label, color) VALUES
        ('work', 'Work', '#3b82f6'),
        ('family', 'Family', '#f472b6'),
        ('meal_prep', 'Meal prep', '#fb923c'),
        ('bathroom', 'Bathroom', '#94a3b8'),
        ('bedroom', 'Bedroom', '#a78bfa'),
        ('watching_tv', 'Watching TV', '#818cf8'),
        ('music', 'Music', '#84cc16'),
        ('podcasts', 'Podcasts', '#65a30d')
        ON CONFLICT (slug) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO activity_rule_configs (
            id, activity_type_slug, enabled, min_duration_minutes,
            merge_gap_minutes, boost_signals, custom_params
        ) VALUES
        (gen_random_uuid(), 'sleep', true, 180, 45,
         '{"watch_confirmed": true}'::jsonb,
         '{"fallback_screen_off_hours": [20, 10]}'::jsonb),
        (gen_random_uuid(), 'work', true, 20, 30, '{}'::jsonb,
         '{"work_days": [0, 1, 2, 3, 6], "work_hours_start": 8, "work_hours_end": 20}'::jsonb),
        (gen_random_uuid(), 'fun', true, 45, 60, '{}'::jsonb, '{}'::jsonb),
        (gen_random_uuid(), 'family', true, 30, 60, '{}'::jsonb, '{}'::jsonb),
        (gen_random_uuid(), 'sport', true, 20, 15,
         '{"watch_active": true, "hevy_open": true}'::jsonb, '{}'::jsonb),
        (gen_random_uuid(), 'meal_prep', true, 10, 10, '{}'::jsonb, '{}'::jsonb),
        (gen_random_uuid(), 'bathroom', true, 2, 5, '{}'::jsonb,
         '{"max_duration_minutes": 15}'::jsonb),
        (gen_random_uuid(), 'bedroom', true, 10, 10, '{}'::jsonb, '{}'::jsonb),
        (gen_random_uuid(), 'watching_tv', true, 20, 15, '{}'::jsonb, '{}'::jsonb),
        (gen_random_uuid(), 'consuming', true, 5, 5, '{}'::jsonb, '{}'::jsonb),
        (gen_random_uuid(), 'music', true, 1, 5, '{}'::jsonb, '{}'::jsonb),
        (gen_random_uuid(), 'podcasts', true, 1, 5, '{}'::jsonb, '{}'::jsonb),
        (gen_random_uuid(), 'communication', true, 3, 5, '{}'::jsonb, '{}'::jsonb),
        (gen_random_uuid(), 'transport', true, 5, 10, '{}'::jsonb, '{}'::jsonb)
        ON CONFLICT (activity_type_slug) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("activity_rule_configs")
