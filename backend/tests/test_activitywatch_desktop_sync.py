import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.connectors.activitywatch.desktop_sync import (
    SOURCE,
    _filter_not_afk,
    _parse_aw_timestamp,
    sync_activitywatch_desktop,
)
from app.models import ActivitySegment, RawEvent


def _load_fixture():
    path = Path(__file__).parent / "fixtures" / "activitywatch_desktop_events.json"
    return json.loads(path.read_text())


def test_parse_aw_timestamp():
    dt = _parse_aw_timestamp("2026-05-12T08:00:00.000000+00:00")
    assert dt == datetime(2026, 5, 12, 8, 0, tzinfo=timezone.utc)


def test_parse_aw_timestamp_z():
    dt = _parse_aw_timestamp("2026-05-12T08:00:00Z")
    assert dt == datetime(2026, 5, 12, 8, 0, tzinfo=timezone.utc)


def test_filter_not_afk_keeps_active():
    window_events = [
        {"timestamp": "2026-05-12T08:00:00+00:00", "duration": 1800, "data": {"app": "Code"}},
    ]
    afk_events = [
        {"timestamp": "2026-05-12T07:50:00+00:00", "duration": 3600, "data": {"status": "not-afk"}},
    ]
    result = _filter_not_afk(window_events, afk_events)
    assert len(result) == 1
    assert result[0]["duration"] == 1800


def test_filter_not_afk_clips():
    window_events = [
        {"timestamp": "2026-05-12T08:00:00+00:00", "duration": 3600, "data": {"app": "Code"}},
    ]
    afk_events = [
        {"timestamp": "2026-05-12T08:00:00+00:00", "duration": 600, "data": {"status": "not-afk"}},
    ]
    result = _filter_not_afk(window_events, afk_events)
    assert len(result) == 1
    assert result[0]["duration"] == 600


def test_filter_not_afk_removes_afk():
    window_events = [
        {"timestamp": "2026-05-12T08:00:00+00:00", "duration": 1800, "data": {"app": "Code"}},
    ]
    afk_events = [
        {"timestamp": "2026-05-12T08:00:00+00:00", "duration": 1800, "data": {"status": "afk"}},
    ]
    result = _filter_not_afk(window_events, afk_events)
    assert len(result) == 0


def test_sync_creates_raw_events_and_segments(db_session):
    events = _load_fixture()

    mock_client = MagicMock()
    mock_client.find_window_bucket.return_value = "aw-watcher-window_testhost"
    mock_client.find_afk_bucket.return_value = None
    mock_client.get_events.return_value = events

    with patch(
        "app.connectors.activitywatch.desktop_sync.ActivityWatchClient",
        return_value=mock_client,
    ):
        result = sync_activitywatch_desktop(db_session, since="7d")

    assert result["raw_upserted"] == 3
    assert result["entries_fetched"] == 3
    assert result["segments_written"] == 3

    raws = db_session.query(RawEvent).filter(RawEvent.source == SOURCE).all()
    assert len(raws) == 3

    segs = db_session.query(ActivitySegment).filter(ActivitySegment.source == SOURCE).all()
    assert len(segs) == 3

    slugs = {s.activity_type_slug for s in segs}
    assert "work" in slugs
    assert "communication" in slugs


def test_sync_idempotent(db_session):
    events = _load_fixture()

    mock_client = MagicMock()
    mock_client.find_window_bucket.return_value = "aw-watcher-window_testhost"
    mock_client.find_afk_bucket.return_value = None
    mock_client.get_events.return_value = events

    with patch(
        "app.connectors.activitywatch.desktop_sync.ActivityWatchClient",
        return_value=mock_client,
    ):
        sync_activitywatch_desktop(db_session, since="7d")
        sync_activitywatch_desktop(db_session, since="7d")

    raws = db_session.query(RawEvent).filter(RawEvent.source == SOURCE).all()
    assert len(raws) == 3
