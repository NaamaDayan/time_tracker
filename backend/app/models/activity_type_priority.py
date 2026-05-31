from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ActivityTypePriority(Base):
    __tablename__ = "activity_type_priorities"

    activity_type_slug: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("activity_types.slug"),
        primary_key=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
