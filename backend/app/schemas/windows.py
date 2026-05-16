from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WindowOut(BaseModel):
    id: int
    started_at: datetime
    ended_at: datetime
    activity_type: str
    activity_label: str
    color: str
    confidence: float
    sources: list[str]
    segment_ids: list[int]
    metadata: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class WindowsResponse(BaseModel):
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    windows: list[WindowOut]
    timezone: str

    model_config = {"populate_by_name": True}
