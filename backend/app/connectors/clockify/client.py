from datetime import datetime
from typing import Any

import httpx

from app.config import get_settings

CLOCKIFY_BASE = "https://api.clockify.me/api/v1"


class ClockifyClient:
    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.clockify_api_key
        if not self.api_key:
            raise ValueError("CLOCKIFY_API_KEY is required")
        self._headers = {"X-Api-Key": self.api_key}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        with httpx.Client(base_url=CLOCKIFY_BASE, headers=self._headers, timeout=60.0) as client:
            response = client.get(path, params=params)
            response.raise_for_status()
            return response.json()

    def get_current_user(self) -> dict[str, Any]:
        return self._get("/user")

    def list_workspaces(self) -> list[dict[str, Any]]:
        return self._get("/workspaces")

    def get_workspace_id(self, workspace_id: str | None = None) -> str:
        if workspace_id:
            return workspace_id
        settings = get_settings()
        if settings.clockify_workspace_id:
            return settings.clockify_workspace_id
        workspaces = self.list_workspaces()
        if not workspaces:
            raise ValueError("No Clockify workspaces found")
        return workspaces[0]["id"]

    def get_time_entries(
        self,
        workspace_id: str,
        user_id: str,
        start: datetime,
        end: datetime,
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self._get(
                f"/workspaces/{workspace_id}/user/{user_id}/time-entries",
                params={
                    "start": start.isoformat().replace("+00:00", "Z"),
                    "end": end.isoformat().replace("+00:00", "Z"),
                    "page-size": page_size,
                    "page": page,
                },
            )
            if not batch:
                break
            entries.extend(batch)
            if len(batch) < page_size:
                break
            page += 1
        return entries
