from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class HabitGoal(Base):
    __tablename__ = "habit_goals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    rule_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class HabitDailyScore(Base):
    __tablename__ = "habit_daily_scores"
    __table_args__ = (
        UniqueConstraint("habit_goal_id", "date", name="uq_habit_daily_scores_goal_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    habit_goal_id: Mapped[int] = mapped_column(ForeignKey("habit_goals.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
