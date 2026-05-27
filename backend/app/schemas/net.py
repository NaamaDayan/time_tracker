from datetime import datetime

from pydantic import BaseModel, Field


class NetSlice(BaseModel):
    activity_type: str
    label: str
    color: str
    seconds: float
    percent: float


class NetResponse(BaseModel):
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    timezone: str
    calendar_days: int
    total_seconds: float
    slices: list[NetSlice]

    model_config = {"populate_by_name": True}
