import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.connectors.google_calendar.sync import (
    event_times_from_payload,
    is_google_calendar_connected,
    sync_google_calendar,
)
from app.connectors.sync_state import upsert_raw_event
from app.models import ActivitySegment, RawEvent, SourceAccount
from app.pipeline.classify import classify_google_calendar_event
from app.pipeline.normalize import rebuild_segments_for_raw_events


@pytest.fixture
def google_events():
    path = Path(__file__).parent / "fixtures" / "google_calendar_events.json"
    return json.loads(path.read_text())


@pytest.fixture
def google_account(db_session):
    account = SourceAccount(
        source="google_calendar",
        display_name="Google Calendar",
        config_json={
            "oauth": {"refresh_token": "test-refresh", "token": "test-token"},
            "calendar_id": "primary",
        },
        is_active=True,
    )
    db_session.add(account)
    for slug, label, color in [
        ("communication", "Communication", "#0ea5e9"),
        ("fun", "Fun", "#ec4899"),
    ]:
        from app.models import ActivityType

        db_session.merge(
            ActivityType(slug=slug, label=label, color=color)
        )
    db_session.commit()
    return account


def test_event_times_from_payload_datetime():
    event = {
        "start": {"dateTime": "2026-05-12T09:00:00Z"},
        "end": {"dateTime": "2026-05-12T10:00:00Z"},
    }
    start, end = event_times_from_payload(event)
    assert start == datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc)


def test_classify_google_calendar_heuristics():
    work_slug, _ = classify_google_calendar_event({"summary": "Sprint planning meeting"})
    assert work_slug == "work"
    fun_slug, _ = classify_google_calendar_event({"summary": "Birthday party"})
    assert fun_slug == "fun"
    default_slug, meta = classify_google_calendar_event({"summary": "Quick chat"})
    assert default_slug == "communication"
    assert meta["summary"] == "Quick chat"


def test_is_google_calendar_connected(google_account):
    assert is_google_calendar_connected(google_account) is True
    google_account.config_json = {}
    assert is_google_calendar_connected(google_account) is False


def test_google_calendar_upsert_idempotent(db_session, google_events):
    entry = google_events[0]
    start, end = event_times_from_payload(entry)
    id1 = upsert_raw_event(
        db_session,
        source="google_calendar",
        external_id=entry["id"],
        started_at=start,
        ended_at=end,
        payload=entry,
    )
    entry2 = {**entry, "summary": "Updated standup"}
    start2, end2 = event_times_from_payload(entry2)
    id2 = upsert_raw_event(
        db_session,
        source="google_calendar",
        external_id=entry2["id"],
        started_at=start2,
        ended_at=end2,
        payload=entry2,
    )
    db_session.commit()
    assert id1 == id2
    assert db_session.query(RawEvent).filter(RawEvent.source == "google_calendar").count() == 1
    raw = db_session.query(RawEvent).one()
    assert raw.payload["summary"] == "Updated standup"


@patch("app.connectors.google_calendar.sync.GoogleCalendarClient")
def test_sync_google_calendar_full(mock_client_cls, db_session, google_account, google_events):
    mock_client = MagicMock()
    mock_client.credentials.token = "refreshed-token"
    mock_client.fetch_incremental_or_full.return_value = (
        google_events,
        "sync-token-abc",
        "full",
    )
    mock_client_cls.return_value = mock_client

    result = sync_google_calendar(db_session)

    assert result["mode"] == "full"
    assert result["entries_fetched"] == 2
    assert result["raw_upserted"] == 2
    assert db_session.query(RawEvent).filter(RawEvent.source == "google_calendar").count() == 2
    assert db_session.query(ActivitySegment).filter(ActivitySegment.source == "google_calendar").count() == 2

    db_session.refresh(google_account)
    assert google_account.config_json["sync_token"] == "sync-token-abc"


@patch("app.connectors.google_calendar.sync.GoogleCalendarClient")
def test_sync_token_incremental(mock_client_cls, db_session, google_account, google_events):
    google_account.config_json = {
        **google_account.config_json,
        "sync_token": "existing-token",
    }
    db_session.commit()

    mock_client = MagicMock()
    mock_client.credentials.token = "token"
    mock_client.fetch_incremental_or_full.return_value = (
        [google_events[0]],
        "sync-token-xyz",
        "incremental",
    )
    mock_client_cls.return_value = mock_client

    result = sync_google_calendar(db_session)
    assert result["mode"] == "incremental"
    mock_client.fetch_incremental_or_full.assert_called_once_with(sync_token="existing-token")


@patch("app.connectors.google_calendar.sync.GoogleCalendarClient")
def test_cancelled_event_removes_raw(mock_client_cls, db_session, google_account, google_events):
    entry = google_events[0]
    start, end = event_times_from_payload(entry)
    raw_id = upsert_raw_event(
        db_session,
        source="google_calendar",
        external_id=entry["id"],
        started_at=start,
        ended_at=end,
        payload=entry,
    )
    rebuild_segments_for_raw_events(db_session, [raw_id])
    db_session.commit()

    cancelled = {**entry, "status": "cancelled"}
    mock_client = MagicMock()
    mock_client.credentials.token = "token"
    mock_client.fetch_incremental_or_full.return_value = ([cancelled], "tok", "incremental")
    mock_client_cls.return_value = mock_client

    sync_google_calendar(db_session)
    assert db_session.query(RawEvent).filter(RawEvent.external_id == entry["id"]).count() == 0
    assert db_session.query(ActivitySegment).count() == 0
