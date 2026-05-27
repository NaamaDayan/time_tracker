import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from app.connectors.dawarich.sync import SOURCE, sync_dawarich
from app.connectors.geofence.schemas import GeofenceEventIn
from app.connectors.geofence.sync import handle_geofence_event
from app.models import ActivitySegment, RawEvent
from app.models.activity import ActivityType


@pytest.fixture
def dawarich_visits():
    path = Path(__file__).parent / "fixtures" / "dawarich_visits.json"
    return json.loads(path.read_text())


@pytest.fixture
def location_types(db_session):
    for slug, label, color in [
        ("sport", "Sport", "#22c55e"),
        ("eat", "Eat", "#f97316"),
    ]:
        if not db_session.query(ActivityType).filter(ActivityType.slug == slug).first():
            db_session.add(ActivityType(slug=slug, label=label, color=color))
    db_session.commit()


def test_dawarich_sync_creates_segments(db_session, location_types, dawarich_visits):
    since = datetime(2026, 5, 21, 0, 0, tzinfo=timezone.utc)
    until = datetime(2026, 5, 22, 0, 0, tzinfo=timezone.utc)

    with patch("app.connectors.dawarich.sync.DawarichClient") as mock_cls:
        mock_cls.return_value.fetch_visits.return_value = dawarich_visits
        result = sync_dawarich(db_session, since=since, until=until)

    assert result["visits_fetched"] == 2
    assert result["raw_upserted"] == 2
    assert result["segments_written"] == 2

    segments = db_session.query(ActivitySegment).filter(ActivitySegment.source == SOURCE).all()
    slugs = {s.activity_type_slug for s in segments}
    assert slugs == {"sport", "eat"}


def test_dawarich_skips_visit_when_geofence_overlaps(db_session, location_types, dawarich_visits):
    enter = GeofenceEventIn(
        zone_name="gym",
        transition="ENTER",
        lat=32.09,
        lon=34.77,
        timestamp=datetime(2026, 5, 21, 18, 0, tzinfo=timezone.utc),
    )
    exit_ev = GeofenceEventIn(
        zone_name="gym",
        transition="EXIT",
        lat=32.09,
        lon=34.77,
        timestamp=datetime(2026, 5, 21, 19, 0, tzinfo=timezone.utc),
    )
    handle_geofence_event(db_session, enter)
    handle_geofence_event(db_session, exit_ev)

    since = datetime(2026, 5, 21, 0, 0, tzinfo=timezone.utc)
    until = datetime(2026, 5, 22, 0, 0, tzinfo=timezone.utc)

    with patch("app.connectors.dawarich.sync.DawarichClient") as mock_cls:
        mock_cls.return_value.fetch_visits.return_value = dawarich_visits
        result = sync_dawarich(db_session, since=since, until=until)

    assert result["skipped_geofence_overlap"] == 1
    dawarich_segments = (
        db_session.query(ActivitySegment).filter(ActivitySegment.source == SOURCE).all()
    )
    assert len(dawarich_segments) == 1
    assert dawarich_segments[0].activity_type_slug == "eat"

    gym_raw = (
        db_session.query(RawEvent)
        .filter(RawEvent.source == SOURCE, RawEvent.external_id == "101")
        .one()
    )
    assert gym_raw.payload.get("_deduped_by_geofence") is True
