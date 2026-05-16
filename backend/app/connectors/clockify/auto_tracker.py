"""Read Clockify Auto Tracker activities from the desktop app's local SQLite DB."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.config import get_settings

logger = logging.getLogger(__name__)

# Core Data stores timestamps as seconds since 2001-01-01 UTC.
CORE_DATA_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)

_MAC_DESKTOP_DIR = Path.home() / "Library/Application Support/Clockify Desktop"
_LINUX_DESKTOP_DIR = Path.home() / ".config/Clockify Desktop"
_WIN_DESKTOP_DIR = Path.home() / "AppData/Roaming/Clockify Desktop"


def _desktop_data_dir() -> Path:
    import sys

    if sys.platform == "darwin":
        return _MAC_DESKTOP_DIR
    if sys.platform == "win32":
        return _WIN_DESKTOP_DIR
    return _LINUX_DESKTOP_DIR


def resolve_desktop_db_path(
    *,
    user_id: str | None = None,
    explicit_path: str | None = None,
) -> Path:
    settings = get_settings()
    if explicit_path:
        path = Path(explicit_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Clockify desktop database not found: {path}")
        return path

    if settings.clockify_desktop_db_path:
        path = Path(settings.clockify_desktop_db_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Clockify desktop database not found: {path}")
        return path

    data_dir = _desktop_data_dir()
    if user_id:
        candidate = data_dir / f"Clockify_{user_id}.sqlite"
        if candidate.is_file():
            return candidate

    if data_dir.is_dir():
        databases = sorted(
            data_dir.glob("Clockify_*.sqlite"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if databases:
            return databases[0]

    raise FileNotFoundError(
        "Clockify Auto Tracker database not found. Install the Clockify desktop app, "
        "enable Auto Tracker (A icon), and record activities — or set CLOCKIFY_DESKTOP_DB_PATH."
    )


def _core_data_to_datetime(value: float | int | None) -> datetime | None:
    if value is None:
        return None
    return CORE_DATA_EPOCH + timedelta(seconds=float(value))


def _user_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().user_timezone)


def _format_clockify_time(dt: datetime) -> str:
    """Emit ISO times in the user's timezone (e.g. Asia/Jerusalem, +03:00)."""
    local = dt.astimezone(_user_timezone())
    return local.isoformat(timespec="seconds")


def _row_to_entry(row: sqlite3.Row) -> dict[str, Any]:
    started = _core_data_to_datetime(row["ZTIMESTARTED"])
    ended = _core_data_to_datetime(row["ZTIMEENDED"])
    if not started or not ended:
        raise ValueError(f"Auto tracker item {row['ZID']} missing start or end time")

    app = (row["ZNAME"] or "").strip()
    window = (row["ZITEMDESCRIPTION"] or "").strip()
    if app and window and app != window:
        description = f"{app} — {window}"
    else:
        description = app or window or ""

    return {
        "id": row["ZID"],
        "description": description,
        "timeInterval": {
            "start": _format_clockify_time(started),
            "end": _format_clockify_time(ended),
        },
        "project": None,
        "tags": [],
        "_autoTracker": {
            "app": app or None,
            "window": window or None,
            "url": row["ZITEMURL"] or None,
            "idleTime": row["ZIDLETIME"],
            "addedToTimesheet": bool(row["ZTIMEENTRYADDED"]),
        },
    }


def fetch_auto_tracker_entries(
    start: datetime,
    end: datetime,
    *,
    user_id: str | None = None,
    db_path: str | None = None,
    include_added_to_timesheet: bool = True,
) -> tuple[list[dict[str, Any]], Path]:
    """Load auto-tracker rows from the desktop SQLite DB within [start, end]."""
    path = resolve_desktop_db_path(user_id=user_id, explicit_path=db_path)
    # Filter range using the user's local calendar boundaries, then compare in UTC.
    user_tz = _user_timezone()
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    start_seconds = (start_utc - CORE_DATA_EPOCH).total_seconds()
    end_seconds = (end_utc - CORE_DATA_EPOCH).total_seconds()

    logger.info(
        "Clockify Auto Tracker: reading %s (range %s .. %s)",
        path,
        start_utc.isoformat(),
        end_utc.isoformat(),
    )

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        added_filter = "" if include_added_to_timesheet else "AND ZTIMEENTRYADDED = 0"
        rows = conn.execute(
            f"""
            SELECT ZID, ZNAME, ZITEMDESCRIPTION, ZITEMURL, ZIDLETIME,
                   ZTIMEENTRYADDED, ZTIMESTARTED, ZTIMEENDED
            FROM ZCDAUTOTRACKERITEM
            WHERE ZTIMESTARTED IS NOT NULL
              AND ZTIMEENDED IS NOT NULL
              AND ZTIMESTARTED < ?
              AND ZTIMEENDED > ?
              {added_filter}
            ORDER BY ZTIMESTARTED ASC
            """,
            (end_seconds, start_seconds),
        ).fetchall()
    finally:
        conn.close()

    entries: list[dict[str, Any]] = []
    for row in rows:
        try:
            entries.append(_row_to_entry(row))
        except ValueError as exc:
            logger.warning("Skipping auto tracker row: %s", exc)

    logger.info("Clockify Auto Tracker: %d activities in range", len(entries))
    return entries, path


def read_desktop_user_id(db_path: Path) -> str | None:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT ZID FROM ZCDUSER LIMIT 1").fetchone()
        return row[0] if row else None
    finally:
        conn.close()
