from datetime import datetime, timedelta, timezone

from app.models import ActivitySegment, ActivityWindow, ActivityWindowSegment
from app.pipeline.normalize import rebuild_segments_for_raw_events
from app.pipeline.windows.service import backfill_all_windows, recompute_windows_for_segments
from app.connectors.sync_state import upsert_raw_event

UTC = timezone.utc


def _add_manual_segment(db_session, start, end, slug="work"):
    seg = ActivitySegment(
        started_at=start,
        ended_at=end,
        activity_type_slug=slug,
        source="manual",
        source_manual=True,
        confidence=1.0,
        raw_event_id=None,
    )
    db_session.add(seg)
    db_session.flush()
    return seg


def test_backfill_merges_fragments(db_session):
    base = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    _add_manual_segment(db_session, base, base + timedelta(minutes=20))
    _add_manual_segment(db_session, base + timedelta(minutes=21), base + timedelta(hours=1))
    db_session.commit()

    written = backfill_all_windows(db_session)
    assert written == 1

    windows = db_session.query(ActivityWindow).all()
    assert len(windows) == 1
    assert windows[0].segment_count == 2
    links = db_session.query(ActivityWindowSegment).all()
    assert len(links) == 2


def test_incremental_after_segment_update(db_session):
    base = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    seg = _add_manual_segment(db_session, base, base + timedelta(minutes=20))
    db_session.commit()
    backfill_all_windows(db_session)

    seg.ended_at = base + timedelta(minutes=40)
    db_session.commit()
    recompute_windows_for_segments(db_session, [seg.id])

    windows = db_session.query(ActivityWindow).all()
    assert len(windows) == 1
    ended = windows[0].ended_at
    if ended.tzinfo is None:
        ended = ended.replace(tzinfo=UTC)
    assert ended == base + timedelta(minutes=40)


def test_cross_source_merge_in_db(db_session):
    base = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    _add_manual_segment(db_session, base, base + timedelta(minutes=20))
    seg2 = ActivitySegment(
        started_at=base + timedelta(minutes=21),
        ended_at=base + timedelta(hours=1),
        activity_type_slug="work",
        source="activitywatch_desktop",
        confidence=1.0,
        raw_event_id=None,
    )
    db_session.add(seg2)
    db_session.commit()

    backfill_all_windows(db_session)
    windows = db_session.query(ActivityWindow).all()
    assert len(windows) == 1
    assert set(windows[0].sources) == {"activitywatch_desktop", "manual"}


def test_manual_segment_merges_with_adjacent_same_type(db_session):
    base = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    _add_manual_segment(db_session, base, base + timedelta(minutes=30))
    db_session.commit()
    backfill_all_windows(db_session)
    assert db_session.query(ActivityWindow).count() == 1

    first_end = db_session.query(ActivityWindow).first().ended_at
    new_manual = _add_manual_segment(
        db_session,
        first_end + timedelta(minutes=3),
        first_end + timedelta(minutes=28),
    )
    db_session.commit()
    recompute_windows_for_segments(db_session, [new_manual.id])
    windows = db_session.query(ActivityWindow).filter(ActivityWindow.activity_type_slug == "work").all()
    assert len(windows) == 1
    assert windows[0].segment_count == 2


def test_rebuild_segments_triggers_windows(db_session):
    started = datetime(2026, 5, 16, 9, 0, tzinfo=UTC)
    ended = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    payload = {"app": "VS Code", "title": "project.py"}
    raw_id = upsert_raw_event(
        db_session,
        source="activitywatch_desktop",
        external_id="aw-rebuild-1",
        started_at=started,
        ended_at=ended,
        payload=payload,
    )
    db_session.commit()
    rebuild_segments_for_raw_events(db_session, [raw_id])

    windows = db_session.query(ActivityWindow).all()
    assert len(windows) >= 1
