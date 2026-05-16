from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ActivityType(Base):
    __tablename__ = "activity_types"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#6366f1")


class ActivitySegment(Base):
    __tablename__ = "activity_segments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activity_type_slug: Mapped[str] = mapped_column(
        String(64), ForeignKey("activity_types.slug"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    raw_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_events.id", ondelete="CASCADE"), nullable=True, index=True
    )

    activity_type: Mapped[ActivityType] = relationship()
    raw_event: Mapped["RawEvent | None"] = relationship(back_populates="segments")  # noqa: F821
