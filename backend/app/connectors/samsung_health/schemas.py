from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class SamsungHealthRecordIn(BaseModel):
    record_type: str
    external_id: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    local_date: date | None = None
    step_count: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SamsungHealthIngestBatch(BaseModel):
    synced_at: datetime
    device_id: str
    records: list[SamsungHealthRecordIn] = Field(default_factory=list)
