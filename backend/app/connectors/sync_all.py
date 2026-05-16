import logging
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.clockify.sync import sync_clockify
from app.connectors.google_calendar.sync import is_google_calendar_connected, sync_google_calendar
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

    try:
        sources["clockify"] = sync_clockify(db, since=since)
    except Exception as e:
        logger.exception("Clockify sync failed")
        errors["clockify"] = str(e)

    account = db.query(SourceAccount).filter(SourceAccount.source == "google_calendar").first()
    if is_google_calendar_connected(account):
        try:
            sources["google_calendar"] = sync_google_calendar(db)
        except Exception as e:
            logger.exception("Google Calendar sync failed")
            errors["google_calendar"] = str(e)
    else:
        logger.info("Google Calendar not connected; skipping sync")

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
