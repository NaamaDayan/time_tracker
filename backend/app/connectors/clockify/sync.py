import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors.clockify.auto_tracker import fetch_auto_tracker_entries, read_desktop_user_id
from app.connectors.clockify.client import ClockifyClient
from app.connectors.sync_state import upsert_raw_event
from app.models import SourceAccount
from app.pipeline.normalize import entry_times_from_payload, rebuild_segments_for_raw_events

logger = logging.getLogger(__name__)


def parse_since(since: str) -> timedelta:
    since = since.strip().lower()
    if since.endswith("d"):
        return timedelta(days=int(since[:-1]))
    if since.endswith("w"):
        return timedelta(weeks=int(since[:-1]))
    raise ValueError(f"Invalid since value: {since}. Use e.g. 7d or 2w")


def _log_clockify_entries(
    entries: list[dict[str, Any]],
    *,
    workspace_id: str,
    user_id: str,
    start: datetime,
    end: datetime,
) -> None:
    settings = get_settings()
    user_tz = ZoneInfo(settings.user_timezone)

    logger.info(
        "Clockify API response: %d time entries (workspace=%s user=%s range=%s .. %s)",
        len(entries),
        workspace_id,
        user_id,
        start.isoformat(),
        end.isoformat(),
    )

    if not entries:
        logger.info("Clockify returned no entries for this range.")
        return

    for i, entry in enumerate(entries, 1):
        interval = entry.get("timeInterval") or {}
        api_start = interval.get("start")
        api_end = interval.get("end")
        running = api_end is None

        started, ended = entry_times_from_payload(entry)
        local_start = started.astimezone(user_tz)
        local_end = ended.astimezone(user_tz)
        duration_min = (ended - started).total_seconds() / 60

        project = entry.get("project") or {}
        project_name = project.get("name") if isinstance(project, dict) else None
        auto = entry.get("_autoTracker") if isinstance(entry.get("_autoTracker"), dict) else {}

        logger.info(
            "Clockify entry [%d/%d] id=%s description=%r project=%r",
            i,
            len(entries),
            entry.get("id"),
            entry.get("description"),
            project_name,
        )
        if auto:
            logger.info(
                "  Auto tracker: app=%r window=%r url=%r",
                auto.get("app"),
                auto.get("window"),
                auto.get("url"),
            )
        logger.info(
            "  API timeInterval: start=%s end=%s%s",
            api_start,
            api_end,
            " (RUNNING — end missing; using sync time as end)" if running else "",
        )
        logger.info(
            "  Parsed UTC:       %s -> %s (%.0f min)",
            started.isoformat(),
            ended.isoformat(),
            duration_min,
        )
        logger.info(
            "  Local (%s): %s -> %s",
            settings.user_timezone,
            local_start.strftime("%Y-%m-%d %H:%M"),
            local_end.strftime("%Y-%m-%d %H:%M"),
        )
        logger.debug("  Raw payload: %s", json.dumps(entry, default=str))


def _resolve_clockify_ids(
    *,
    api_key: str | None,
    desktop_user_id: str | None,
) -> tuple[str | None, str | None]:
    settings = get_settings()
    user_id = desktop_user_id
    workspace_id = settings.clockify_workspace_id or None

    if api_key or settings.clockify_api_key:
        try:
            client = ClockifyClient(api_key=api_key)
            user = client.get_current_user()
            user_id = user["id"]
            workspace_id = client.get_workspace_id()
        except Exception as exc:
            logger.warning("Clockify API unavailable for account metadata: %s", exc)

    return workspace_id, user_id


def sync_clockify(
    db: Session,
    *,
    since: str = "7d",
    start: datetime | None = None,
    end: datetime | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if end is None:
        end = now
    if start is None:
        start = end - parse_since(since)

    logger.info("Clockify sync starting (since=%s, source=auto_tracker)", since)
    entries, db_path = fetch_auto_tracker_entries(start, end)
    desktop_user_id = read_desktop_user_id(db_path)
    workspace_id, user_id = _resolve_clockify_ids(
        api_key=api_key,
        desktop_user_id=desktop_user_id,
    )
    _log_clockify_entries(
        entries,
        workspace_id=workspace_id or "local",
        user_id=user_id or "local",
        start=start,
        end=end,
    )

    account = db.query(SourceAccount).filter(SourceAccount.source == "clockify").first()
    if account:
        account.config_json = {
            "workspace_id": workspace_id,
            "user_id": user_id,
            "desktop_db": str(db_path),
            "source": "auto_tracker",
        }
    db.commit()

    raw_upserted = 0
    touched_ids: list[int] = []

    for entry in entries:
        started, ended = entry_times_from_payload(entry)
        raw_id = upsert_raw_event(
            db,
            source="clockify",
            external_id=entry["id"],
            started_at=started,
            ended_at=ended,
            payload=entry,
        )
        touched_ids.append(raw_id)
        raw_upserted += 1

    db.commit()
    segments_written = rebuild_segments_for_raw_events(db, touched_ids)

    logger.info(
        "Clockify sync done: upserted=%s segments=%s",
        raw_upserted,
        segments_written,
    )

    return {
        "raw_upserted": raw_upserted,
        "segments_written": segments_written,
        "entries_fetched": len(entries),
        "workspace_id": workspace_id,
        "source": "auto_tracker",
        "desktop_db": str(db_path),
    }
