from datetime import datetime, timedelta, timezone

import pytest

from app.models import ActivitySegment, RawEvent
from app.pipeline.confidence import score_segment_confidence

UTC = timezone.utc


def test_gps_long_duration_high_confidence(db_session):
    started = datetime(2026, 5, 22, 10, 0, tzinfo=UTC)
    ended = started + timedelta(minutes=45)
    raw = RawEvent(
        source="geofence",
        external_id="gym_enter_1",
        started_at=started,
        ended_at=ended,
        payload={"zone_name": "gym", "transition": "ENTER"},
    )
    score = score_segment_confidence(
        raw,
        activity_type_slug="sport",
        source="geofence",
        metadata={"zone_name": "gym"},
        db=db_session,
        started_at=started,
        ended_at=ended,
    )
    assert score >= 0.8


def test_activitywatch_only_low_confidence(db_session):
    started = datetime(2026, 5, 22, 9, 0, tzinfo=UTC)
    ended = started + timedelta(minutes=8)
    raw = RawEvent(
        source="activitywatch_desktop",
        external_id="aw_1",
        started_at=started,
        ended_at=ended,
        payload={"app": "Chrome"},
    )
    score = score_segment_confidence(
        raw,
        activity_type_slug="work",
        source="activitywatch_desktop",
        metadata={},
        db=db_session,
        started_at=started,
        ended_at=ended,
    )
    assert score < 0.7


def test_derive_window_confidence_min(db_session):
    from app.models import ActivityWindow, ActivityWindowSegment
    from app.pipeline.confidence import derive_window_confidence

    base = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    s1 = ActivitySegment(
        started_at=base,
        ended_at=base + timedelta(minutes=30),
        activity_type_slug="work",
        source="manual",
        source_manual=True,
        confidence=0.9,
    )
    s2 = ActivitySegment(
        started_at=base + timedelta(minutes=31),
        ended_at=base + timedelta(hours=1),
        activity_type_slug="work",
        source="manual",
        source_manual=True,
        confidence=0.5,
    )
    db_session.add_all([s1, s2])
    db_session.flush()
    win = ActivityWindow(
        activity_type_slug="work",
        started_at=base,
        ended_at=base + timedelta(hours=1),
        confidence=0.5,
        sources=["manual"],
        segment_count=2,
        computed_at=base,
    )
    db_session.add(win)
    db_session.flush()
    db_session.add(ActivityWindowSegment(window_id=win.id, segment_id=s1.id))
    db_session.add(ActivityWindowSegment(window_id=win.id, segment_id=s2.id))
    db_session.commit()
    assert derive_window_confidence(win.id, db_session) == 0.5
