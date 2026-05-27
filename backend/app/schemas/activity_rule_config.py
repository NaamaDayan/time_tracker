import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ActivityRuleConfigOut(BaseModel):
    id: uuid.UUID
    activity_type_slug: str
    enabled: bool
    min_duration_minutes: int
    merge_gap_minutes: int
    boost_signals: dict[str, Any]
    custom_params: dict[str, Any]
    updated_at: datetime

    model_config = {"from_attributes": True}


class ActivityRuleConfigUpdate(BaseModel):
    enabled: bool | None = None
    min_duration_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    merge_gap_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    boost_signals: dict[str, Any] | None = None
    custom_params: dict[str, Any] | None = None


class PreviewSegmentOut(BaseModel):
    id: int
    started_at: datetime
    ended_at: datetime
    duration_minutes: float
    source: str


class PreviewResponse(BaseModel):
    segment_count: int
    total_minutes: float
    sample_segments: list[PreviewSegmentOut]
