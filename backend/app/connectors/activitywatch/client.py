import logging
from datetime import datetime
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class ActivityWatchClient:
    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.activitywatch_base_url).rstrip("/")

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/api/0{path}"
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    def list_buckets(self) -> dict[str, Any]:
        return self._get("/buckets/")

    def get_events(
        self,
        bucket_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = -1,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if start is not None:
            params["start"] = start.isoformat()
        if end is not None:
            params["end"] = end.isoformat()
        return self._get(f"/buckets/{bucket_id}/events", params=params)

    def find_bucket(self, prefix: str) -> str | None:
        """Find the first bucket whose ID starts with *prefix*."""
        buckets = self.list_buckets()
        for bucket_id in buckets:
            if bucket_id.startswith(prefix):
                return bucket_id
        return None

    def find_window_bucket(self) -> str | None:
        return self.find_bucket("aw-watcher-window")

    def find_afk_bucket(self) -> str | None:
        return self.find_bucket("aw-watcher-afk")
