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
        source="clockify",
        confidence=1.0,
        raw_event_id=None,
    )
    db_session.add(seg2)
    db_session.commit()

    backfill_all_windows(db_session)
    windows = db_session.query(ActivityWindow).all()
    assert len(windows) == 1
    assert set(windows[0].sources) == {"clockify", "manual"}


def test_rebuild_segments_triggers_windows(db_session, clockify_entries):
    entry = clockify_entries[0]
    started, ended = datetime(2026, 5, 16, 9, 0, tzinfo=UTC), datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    raw_id = upsert_raw_event(
        db_session,
        source="clockify",
        external_id=entry["id"],
        started_at=started,
        ended_at=ended,
        payload=entry,
    )
    db_session.commit()
    rebuild_segments_for_raw_events(db_session, [raw_id])

    windows = db_session.query(ActivityWindow).all()
    assert len(windows) >= 1
