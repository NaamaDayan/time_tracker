import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.google_calendar.client import GoogleCalendarClient, OAuthRevokedException
from app.connectors.sync_state import (
    delete_raw_event,
    read_sync_state,
    upsert_raw_event,
    write_sync_state,
)
from app.models import SourceAccount
from app.pipeline.normalize import rebuild_segments_for_raw_events

logger = logging.getLogger(__name__)

SOURCE = "google_calendar"


def _parse_google_datetime(value: str, *, is_end: bool = False) -> datetime:
    if "T" in value:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    d = date.fromisoformat(value)
    if is_end:
        # All-day end date is exclusive in Google Calendar
        d = d - timedelta(days=1)
        return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)


def event_times_from_payload(event: dict[str, Any]) -> tuple[datetime, datetime]:
    start = event.get("start") or {}
    end = event.get("end") or {}
    if "dateTime" in start:
        started = _parse_google_datetime(start["dateTime"])
        ended = _parse_google_datetime(end.get("dateTime", start["dateTime"]), is_end=True)
    else:
        started = _parse_google_datetime(start["date"])
        ended = _parse_google_datetime(end.get("date", start["date"]), is_end=True)
    if ended <= started:
        ended = started + timedelta(minutes=30)
    return started, ended


def is_google_calendar_connected(account: SourceAccount | None) -> bool:
    if not account or not account.is_active:
        return False
    state = read_sync_state(account)
    oauth = state.get("oauth") or {}
    return bool(oauth.get("refresh_token"))


def sync_google_calendar(db: Session) -> dict[str, Any]:
    account = db.query(SourceAccount).filter(SourceAccount.source == SOURCE).first()
    if not account:
        raise ValueError("Google Calendar source account not configured")

    state = read_sync_state(account)
    oauth = state.get("oauth") or {}
    if not oauth.get("refresh_token"):
        raise ValueError("Google Calendar not connected. Complete OAuth first.")

    calendar_id = state.get("calendar_id", "primary")
    sync_token = state.get("sync_token")

    try:
        client = GoogleCalendarClient(oauth, calendar_id=calendar_id)
        events, next_sync_token, mode = client.fetch_incremental_or_full(sync_token=sync_token)
    except OAuthRevokedException:
        logger.warning("Google Calendar OAuth revoked; clearing stored credentials")
        write_sync_state(db, account, oauth={}, sync_token=None)
        raise

    raw_upserted = 0
    deleted = 0
    touched_ids: list[int] = []

    for event in events:
        external_id = event.get("id")
        if not external_id:
            continue

        if event.get("status") == "cancelled":
            removed_id = delete_raw_event(db, source=SOURCE, external_id=external_id)
            if removed_id is not None:
                deleted += 1
            continue

        started, ended = event_times_from_payload(event)
        raw_id = upsert_raw_event(
            db,
            source=SOURCE,
            external_id=external_id,
            started_at=started,
            ended_at=ended,
            payload=event,
        )
        touched_ids.append(raw_id)
        raw_upserted += 1

    db.commit()
    segments_written = rebuild_segments_for_raw_events(db, touched_ids)

    now = datetime.now(timezone.utc)
    updates: dict[str, Any] = {"last_sync_at": now.isoformat()}
    if next_sync_token:
        updates["sync_token"] = next_sync_token
    if client.credentials.token:
        updates["oauth"] = {**oauth, "token": client.credentials.token}
    write_sync_state(db, account, **updates)

    logger.info(
        "Google Calendar sync done: mode=%s upserted=%s deleted=%s segments=%s",
        mode,
        raw_upserted,
        deleted,
        segments_written,
    )

    return {
        "raw_upserted": raw_upserted,
        "segments_written": segments_written,
        "entries_fetched": len(events),
        "deleted": deleted,
        "mode": mode,
    }
