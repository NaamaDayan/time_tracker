from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ActivityWindow(Base):
    """Gap-merged presentation layer built from activity_segments (Layer 3)."""

    __tablename__ = "activity_windows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_type_slug: Mapped[str] = mapped_column(
        String(64), ForeignKey("activity_types.slug"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    sources: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    activity_type: Mapped["ActivityType"] = relationship()  # noqa: F821
    window_segments: Mapped[list["ActivityWindowSegment"]] = relationship(
        back_populates="window", cascade="all, delete-orphan"
    )


class ActivityWindowSegment(Base):
    """Provenance: which classified segments compose a merged window."""

    __tablename__ = "activity_window_segments"
    __table_args__ = (
        UniqueConstraint("segment_id", name="uq_activity_window_segments_segment_id"),
    )

    window_id: Mapped[int] = mapped_column(
        ForeignKey("activity_windows.id", ondelete="CASCADE"), primary_key=True
    )
    segment_id: Mapped[int] = mapped_column(
        ForeignKey("activity_segments.id", ondelete="CASCADE"), primary_key=True
    )

    window: Mapped[ActivityWindow] = relationship(back_populates="window_segments")
    segment: Mapped["ActivitySegment"] = relationship()  # noqa: F821
