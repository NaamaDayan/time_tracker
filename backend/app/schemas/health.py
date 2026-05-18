from datetime import date, datetime

from pydantic import BaseModel, Field


class DailyHealthStat(BaseModel):
    local_date: date
    step_count: int | None = None
    calories_burned: float | None = None


class HealthDailyStatsResponse(BaseModel):
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    timezone: str
    days: list[DailyHealthStat]
