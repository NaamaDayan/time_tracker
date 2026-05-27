from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SegmentOut(BaseModel):
    id: int
    started_at: datetime
    ended_at: datetime | None = None
    activity_type: str
    activity_label: str
    color: str
    source: str
    confidence: float
    metadata: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class TimelineResponse(BaseModel):
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    segments: list[SegmentOut]
    timezone: str

    model_config = {"populate_by_name": True}
