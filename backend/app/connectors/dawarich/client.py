import logging
from datetime import datetime
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class DawarichClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.dawarich_base_url).rstrip("/")
        self.api_key = api_key or settings.dawarich_api_key

    def fetch_visits(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        if not self.api_key:
            raise ValueError("DAWARICH_API_KEY is not configured")

        params = {
            "start_at": start.isoformat().replace("+00:00", "Z"),
            "end_at": end.isoformat().replace("+00:00", "Z"),
            "api_key": self.api_key,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/api/v1/visits"

        with httpx.Client(timeout=60.0) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("visits", "data", "results"):
                if isinstance(data.get(key), list):
                    return data[key]
        logger.warning("Unexpected Dawarich visits response shape: %s", type(data))
        return []
