import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.gps_zone import UUIDType


class ActivityRuleConfig(Base):
    __tablename__ = "activity_rule_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(), primary_key=True, default=uuid.uuid4
    )
    activity_type_slug: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("activity_types.slug"),
        nullable=False,
        unique=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    merge_gap_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    boost_signals: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    custom_params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
