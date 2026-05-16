from typing import Any

from pydantic import BaseModel


class SyncRequest(BaseModel):
    since: str = "7d"


class SyncSourceResult(BaseModel):
    raw_upserted: int = 0
    segments_written: int = 0
    entries_fetched: int = 0
    workspace_id: str | None = None


class SyncResponse(BaseModel):
    since: str = "7d"
    raw_upserted: int
    segments_written: int
    entries_fetched: int
    sources: dict[str, SyncSourceResult | dict[str, Any]] = {}
    errors: dict[str, str] = {}
    workspace_id: str | None = None  # legacy field from single-source sync
