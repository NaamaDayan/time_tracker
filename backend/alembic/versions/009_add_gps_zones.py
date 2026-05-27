"""add gps_zones table

Revision ID: 009
Revises: 008
Create Date: 2026-05-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gps_zones",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column(
            "activity_type_slug",
            sa.String(64),
            sa.ForeignKey("activity_types.slug"),
            nullable=True,
        ),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lon", sa.Float, nullable=False),
        sa.Column("radius_meters", sa.Integer, nullable=False, server_default="150"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.execute(
        """
        INSERT INTO gps_zones (id, name, category, activity_type_slug, lat, lon, radius_meters)
        VALUES
            (gen_random_uuid(), 'home', 'home', NULL, 32.08413342503022, 34.78651329136993, 50),
            (gen_random_uuid(), 'office', 'work', 'work', 32.14380730234709, 4.80071555285304, 120),
            (gen_random_uuid(), 'gym', 'gym', 'sport', 32.079459239355764, 34.78153963806355, 80),
            (gen_random_uuid(), 'parents', 'family', 'fun', 32.09655905352153, 34.800793724015435, 100)
        ON CONFLICT (name) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("gps_zones")
