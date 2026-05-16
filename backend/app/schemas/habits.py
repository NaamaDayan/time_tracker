from typing import Any

from pydantic import BaseModel


class HabitDailyOut(BaseModel):
    date: str
    score: float | None
    details: dict[str, Any] | None = None


class HabitGoalOut(BaseModel):
    slug: str
    name: str
    week_score: float
    daily: list[HabitDailyOut]


class HabitWeeklyResponse(BaseModel):
    week: str
    timezone: str
    goals: list[HabitGoalOut]
