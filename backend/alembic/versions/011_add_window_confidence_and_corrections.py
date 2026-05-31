"""add window confidence and corrections

Revision ID: 011
Revises: 010
Create Date: 2026-05-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "activity_windows",
        sa.Column("confirmed_by_user", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "activity_windows",
        sa.Column("dismissed_by_user", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "activity_windows",
        sa.Column("correction_of_window_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_activity_windows_correction_of_window_id",
        "activity_windows",
        "activity_windows",
        ["correction_of_window_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_activity_windows_correction_of_window_id",
        "activity_windows",
        ["correction_of_window_id"],
    )

    op.add_column(
        "activity_segments",
        sa.Column("source_manual", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.execute(
        sa.text(
            "UPDATE activity_segments SET source_manual = true WHERE source = 'manual'"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_activity_windows_correction_of_window_id", table_name="activity_windows")
    op.drop_constraint(
        "fk_activity_windows_correction_of_window_id",
        "activity_windows",
        type_="foreignkey",
    )
    op.drop_column("activity_windows", "correction_of_window_id")
    op.drop_column("activity_windows", "dismissed_by_user")
    op.drop_column("activity_windows", "confirmed_by_user")
    op.drop_column("activity_segments", "source_manual")
