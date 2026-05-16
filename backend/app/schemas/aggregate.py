from datetime import datetime

from pydantic import BaseModel, Field


class ActivityTypeOut(BaseModel):
    slug: str
    label: str
    color: str

    model_config = {"from_attributes": True}


class AggregateSlice(BaseModel):
    activity_type: str
    label: str
    color: str
    seconds: float
    percent: float


class AggregateResponse(BaseModel):
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    timezone: str
    total_seconds: float
    unattributed_seconds: float
    slices: list[AggregateSlice]

    model_config = {"populate_by_name": True}
