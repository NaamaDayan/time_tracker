import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from app.connectors.google_calendar.oauth import credentials_from_oauth

logger = logging.getLogger(__name__)

INITIAL_BACKFILL_DAYS = 30
FORWARD_BUFFER_DAYS = 7


class GoogleCalendarClient:
    def __init__(self, oauth_data: dict[str, Any], *, calendar_id: str = "primary"):
        creds = credentials_from_oauth(oauth_data)
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request

            creds.refresh(Request())
        self._creds = creds
        self._calendar_id = calendar_id
        self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    @property
    def credentials(self) -> Credentials:
        return self._creds

    def list_events(
        self,
        *,
        sync_token: str | None = None,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Return (events, next_sync_token). Raises HttpError; 410 means sync token expired."""
        events: list[dict[str, Any]] = []
        page_token: str | None = None
        next_sync_token: str | None = None

        while True:
            kwargs: dict[str, Any] = {
                "calendarId": self._calendar_id,
                "singleEvents": True,
                "showDeleted": True,
                "maxResults": 250,
            }
            if sync_token:
                kwargs["syncToken"] = sync_token
            else:
                if time_min:
                    kwargs["timeMin"] = time_min.isoformat()
                if time_max:
                    kwargs["timeMax"] = time_max.isoformat()
                kwargs["orderBy"] = "startTime"

            if page_token:
                kwargs["pageToken"] = page_token

            result = self._service.events().list(**kwargs).execute()
            events.extend(result.get("items", []))
            page_token = result.get("nextPageToken")
            if result.get("nextSyncToken"):
                next_sync_token = result["nextSyncToken"]
            if not page_token:
                break

        logger.info(
            "Google Calendar list: %d events (sync_token=%s)",
            len(events),
            "yes" if sync_token else "no",
        )
        return events, next_sync_token

    def fetch_incremental_or_full(
        self,
        *,
        sync_token: str | None,
    ) -> tuple[list[dict[str, Any]], str | None, str]:
        """Returns (events, next_sync_token, mode). mode is 'incremental' or 'full'."""
        try:
            if sync_token:
                events, token = self.list_events(sync_token=sync_token)
                return events, token, "incremental"
        except HttpError as e:
            if e.resp.status != 410:
                raise
            logger.warning("Google Calendar sync token expired (410); running full sync")

        now = datetime.now(timezone.utc)
        time_min = now - timedelta(days=INITIAL_BACKFILL_DAYS)
        time_max = now + timedelta(days=FORWARD_BUFFER_DAYS)
        events, token = self.list_events(time_min=time_min, time_max=time_max)
        return events, token, "full"
