from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ActivityWatchRecordIn(BaseModel):
    record_type: str = "app_session"
    external_id: str
    started_at: datetime
    ended_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class ActivityWatchIngestBatch(BaseModel):
    synced_at: datetime
    device_id: str
    records: list[ActivityWatchRecordIn] = Field(default_factory=list)
