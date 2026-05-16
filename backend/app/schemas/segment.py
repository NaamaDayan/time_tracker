from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SegmentCreate(BaseModel):
    started_at: datetime
    ended_at: datetime
    activity_type: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=256)
    all_day: bool = False

    @field_validator("ended_at")
    @classmethod
    def end_after_start(cls, ended_at: datetime, info) -> datetime:
        started = info.data.get("started_at")
        if started is not None and ended_at <= started:
            raise ValueError("ended_at must be after started_at")
        return ended_at


class SegmentUpdate(BaseModel):
    started_at: datetime | None = None
    ended_at: datetime | None = None
    activity_type: str | None = Field(default=None, min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=256)
    all_day: bool | None = None


class SegmentMutationOut(BaseModel):
    id: int
    started_at: datetime
    ended_at: datetime
    activity_type: str
    activity_label: str
    color: str
    source: str
    confidence: float
    metadata: dict[str, Any] | None = None

    model_config = {"from_attributes": True}
