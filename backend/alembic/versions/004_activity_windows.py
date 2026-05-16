"""activity windows aggregation layer

Revision ID: 004
Revises: 003
Create Date: 2026-05-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_windows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("activity_type_slug", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("segment_count", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["activity_type_slug"], ["activity_types.slug"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_activity_windows_activity_type_started",
        "activity_windows",
        ["activity_type_slug", "started_at"],
    )
    op.create_index(
        "ix_activity_windows_started_ended",
        "activity_windows",
        ["started_at", "ended_at"],
    )

    op.create_table(
        "activity_window_segments",
        sa.Column("window_id", sa.Integer(), nullable=False),
        sa.Column("segment_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["window_id"], ["activity_windows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["segment_id"], ["activity_segments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("window_id", "segment_id"),
        sa.UniqueConstraint("segment_id", name="uq_activity_window_segments_segment_id"),
    )

    op.create_index(
        "ix_activity_segments_type_started",
        "activity_segments",
        ["activity_type_slug", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_activity_segments_type_started", table_name="activity_segments")
    op.drop_table("activity_window_segments")
    op.drop_index("ix_activity_windows_started_ended", table_name="activity_windows")
    op.drop_index("ix_activity_windows_activity_type_started", table_name="activity_windows")
    op.drop_table("activity_windows")
