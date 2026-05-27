import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors.activitywatch.desktop_sync import sync_activitywatch_desktop
from app.connectors.dawarich.sync import sync_dawarich
from app.connectors.google_calendar.sync import is_google_calendar_connected, sync_google_calendar
from app.connectors.utils import parse_since
from app.models import SourceAccount

logger = logging.getLogger(__name__)


def sync_all_sources(
    db: Session,
    *,
    since: str = "7d",
) -> dict[str, Any]:
    """Run every configured source connector. Add new sources here."""
    sources: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}

    logger.info("Sync all sources (since=%s)", since)

    settings = get_settings()

    if settings.activitywatch_poll_enabled:
        try:
            sources["activitywatch_desktop"] = sync_activitywatch_desktop(db, since=since)
        except Exception as e:
            logger.exception("ActivityWatch Desktop sync failed")
            errors["activitywatch_desktop"] = str(e)
    else:
        logger.info("ActivityWatch Desktop polling disabled; skipping sync")

    account = db.query(SourceAccount).filter(SourceAccount.source == "google_calendar").first()
    if is_google_calendar_connected(account):
        try:
            sources["google_calendar"] = sync_google_calendar(db)
        except Exception as e:
            logger.exception("Google Calendar sync failed")
            errors["google_calendar"] = str(e)
    else:
        logger.info("Google Calendar not connected; skipping sync")

    if settings.dawarich_sync_enabled and settings.dawarich_api_key:
        try:
            since_dt = datetime.now(timezone.utc) - parse_since(since)
            sources["dawarich"] = sync_dawarich(db, since=since_dt)
        except Exception as e:
            logger.exception("Dawarich sync failed")
            errors["dawarich"] = str(e)
    else:
        logger.info("Dawarich not configured; skipping sync")

    raw_upserted = sum(s.get("raw_upserted", 0) for s in sources.values())
    segments_written = sum(s.get("segments_written", 0) for s in sources.values())
    entries_fetched = sum(s.get("entries_fetched", 0) for s in sources.values())

    logger.info(
        "Sync all complete: sources_ok=%s errors=%s raw=%s segments=%s",
        list(sources.keys()),
        list(errors.keys()),
        raw_upserted,
        segments_written,
    )

    return {
        "since": since,
        "sources": sources,
        "errors": errors,
        "raw_upserted": raw_upserted,
        "segments_written": segments_written,
        "entries_fetched": entries_fetched,
    }
