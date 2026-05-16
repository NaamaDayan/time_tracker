import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.connectors.clockify.auto_tracker import (
    CORE_DATA_EPOCH,
    fetch_auto_tracker_entries,
    resolve_desktop_db_path,
)


def _seconds_since_core_data(dt: datetime) -> float:
    return (dt.astimezone(timezone.utc) - CORE_DATA_EPOCH).total_seconds()


@pytest.fixture
def desktop_db(tmp_path: Path) -> Path:
    path = tmp_path / "Clockify_testuser.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE ZCDAUTOTRACKERITEM (
            Z_PK INTEGER PRIMARY KEY,
            ZID VARCHAR UNIQUE,
            ZNAME VARCHAR,
            ZITEMDESCRIPTION VARCHAR,
            ZITEMURL VARCHAR,
            ZIDLETIME FLOAT,
            ZTIMEENTRYADDED INTEGER,
            ZTIMESTARTED TIMESTAMP,
            ZTIMEENDED TIMESTAMP
        )
        """
    )
    start = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 16, 10, 30, tzinfo=timezone.utc)
    conn.execute(
        """
        INSERT INTO ZCDAUTOTRACKERITEM (
            ZID, ZNAME, ZITEMDESCRIPTION, ZITEMURL, ZIDLETIME,
            ZTIMEENTRYADDED, ZTIMESTARTED, ZTIMEENDED
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "auto-1",
            "Google Chrome",
            "GitHub",
            "https://github.com",
            0.1,
            0,
            _seconds_since_core_data(start),
            _seconds_since_core_data(end),
        ),
    )
    conn.commit()
    conn.close()
    return path


def test_fetch_auto_tracker_entries(desktop_db: Path):
    start = datetime(2026, 5, 16, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 17, 0, 0, tzinfo=timezone.utc)
    entries, used_path = fetch_auto_tracker_entries(
        start, end, db_path=str(desktop_db)
    )
    assert used_path == desktop_db
    assert len(entries) == 1
    assert entries[0]["id"] == "auto-1"
    assert entries[0]["description"] == "Google Chrome — GitHub"
    assert entries[0]["timeInterval"]["start"] == "2026-05-16T13:00:00+03:00"
    assert entries[0]["_autoTracker"]["app"] == "Google Chrome"


def test_fetch_auto_tracker_entries_outside_range(desktop_db: Path):
    start = datetime(2026, 5, 10, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 11, 0, 0, tzinfo=timezone.utc)
    entries, _ = fetch_auto_tracker_entries(start, end, db_path=str(desktop_db))
    assert entries == []


def test_resolve_desktop_db_path_explicit(desktop_db: Path):
    assert resolve_desktop_db_path(explicit_path=str(desktop_db)) == desktop_db


def test_resolve_desktop_db_path_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        resolve_desktop_db_path(explicit_path=str(tmp_path / "missing.sqlite"))
