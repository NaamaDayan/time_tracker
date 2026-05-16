"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_types",
        sa.Column("slug", sa.String(64), primary_key=True),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("color", sa.String(16), nullable=False),
    )
    op.create_table(
        "source_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("config_json", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source"),
    )
    op.create_table(
        "raw_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(256), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_raw_events_source_external_id"),
    )
    op.create_index("ix_raw_events_source", "raw_events", ["source"])
    op.create_index("ix_raw_events_started_at", "raw_events", ["started_at"])
    op.create_table(
        "activity_segments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activity_type_slug", sa.String(64), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("raw_event_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["activity_type_slug"], ["activity_types.slug"]),
        sa.ForeignKeyConstraint(["raw_event_id"], ["raw_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activity_segments_started_at", "activity_segments", ["started_at"])
    op.create_index("ix_activity_segments_source", "activity_segments", ["source"])
    op.create_index("ix_activity_segments_raw_event_id", "activity_segments", ["raw_event_id"])
    op.create_table(
        "habit_goals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("rule_json", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "habit_daily_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("habit_goal_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["habit_goal_id"], ["habit_goals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("habit_goal_id", "date", name="uq_habit_daily_scores_goal_date"),
    )
    op.create_index("ix_habit_daily_scores_date", "habit_daily_scores", ["date"])

    # Seed activity types
    op.execute(
        """
        INSERT INTO activity_types (slug, label, color) VALUES
        ('work', 'Work', '#3b82f6'),
        ('screen_time', 'Screen time', '#8b5cf6')
        """
    )
    # Seed habit goals
    op.execute(
        """
        INSERT INTO habit_goals (slug, name, rule_json, is_active) VALUES
        (
            'weekday_work_target',
            'Weekday work (6h+)',
            '{"type": "daily_duration", "activity": "work", "min_seconds": 21600, "days": [0,1,2,3,4]}',
            true
        ),
        (
            'weekend_work_cap',
            'Weekend work cap (2h)',
            '{"type": "daily_duration_cap", "activity": "work", "max_seconds": 7200, "days": [5,6]}',
            true
        ),
        (
            'weekly_work_total',
            'Weekly work (40h)',
            '{"type": "weekly_duration", "activity": "work", "target_seconds": 144000}',
            true
        )
        """
    )
    op.execute(
        """
        INSERT INTO source_accounts (source, display_name, config_json, is_active)
        VALUES ('clockify', 'Clockify', '{}', true)
        """
    )


def downgrade() -> None:
    op.drop_table("habit_daily_scores")
    op.drop_table("habit_goals")
    op.drop_table("activity_segments")
    op.drop_table("raw_events")
    op.drop_table("source_accounts")
    op.drop_table("activity_types")
