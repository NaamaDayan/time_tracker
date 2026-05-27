import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.connectors.geofence.schemas import GeofenceEventIn
from app.connectors.geofence.sync import SOURCE, handle_geofence_event
from app.models import ActivitySegment, RawEvent
from app.models.activity import ActivityType


@pytest.fixture
def location_activity_types(db_session):
    for slug, label, color in [
        ("sport", "Sport", "#22c55e"),
        ("work", "Work", "#3b82f6"),
    ]:
        if not db_session.query(ActivityType).filter(ActivityType.slug == slug).first():
            db_session.add(ActivityType(slug=slug, label=label, color=color))
    db_session.commit()


@pytest.fixture
def geofence_events():
    path = Path(__file__).parent / "fixtures" / "geofence_enter_exit.json"
    data = json.loads(path.read_text())
    return {
        "enter": GeofenceEventIn.model_validate(data["enter"]),
        "exit": GeofenceEventIn.model_validate(data["exit"]),
    }


def test_geofence_enter_exit_creates_closed_segment(
    db_session, location_activity_types, geofence_events
):
    enter = geofence_events["enter"]
    exit_ev = geofence_events["exit"]

    r1 = handle_geofence_event(db_session, enter)
    assert r1["segment_id"] is not None

    open_seg = (
        db_session.query(ActivitySegment)
        .filter(ActivitySegment.source == SOURCE, ActivitySegment.ended_at.is_(None))
        .one()
    )
    assert open_seg.activity_type_slug == "sport"
    assert open_seg.metadata_["zone_name"] == "gym"

    r2 = handle_geofence_event(db_session, exit_ev)
    assert r2["segment_id"] == open_seg.id

    db_session.refresh(open_seg)
    assert open_seg.ended_at is not None
    ended = open_seg.ended_at.replace(tzinfo=timezone.utc) if open_seg.ended_at.tzinfo is None else open_seg.ended_at
    assert ended == datetime(2026, 5, 22, 10, 45, tzinfo=timezone.utc)

    raw_count = db_session.query(RawEvent).filter(RawEvent.source == SOURCE).count()
    assert raw_count == 2


def test_geofence_enter_idempotent_external_id(db_session, location_activity_types, geofence_events):
    enter = geofence_events["enter"]
    handle_geofence_event(db_session, enter)
    handle_geofence_event(db_session, enter)

    open_segments = (
        db_session.query(ActivitySegment)
        .filter(ActivitySegment.source == SOURCE, ActivitySegment.ended_at.is_(None))
        .all()
    )
    assert len(open_segments) == 1
