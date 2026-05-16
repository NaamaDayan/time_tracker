from datetime import datetime, timezone

from app.models import ActivitySegment, RawEvent
from app.pipeline.normalize import entry_times_from_payload, rebuild_segments_for_raw_events


def test_entry_times_from_payload():
    entry = {
        "id": "e1",
        "timeInterval": {"start": "2026-05-12T08:00:00Z", "end": "2026-05-12T10:00:00Z"},
    }
    start, end = entry_times_from_payload(entry)
    assert start == datetime(2026, 5, 12, 8, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc)


def test_raw_event_upsert_idempotent(db_session, clockify_entries):
    now = datetime.now(timezone.utc)
    ids = []
    for entry in clockify_entries:
        started, ended = entry_times_from_payload(entry)
        raw = RawEvent(
            source="clockify",
            external_id=entry["id"],
            started_at=started,
            ended_at=ended,
            payload=entry,
            ingested_at=now,
        )
        db_session.add(raw)
        db_session.flush()
        ids.append(raw.id)
    db_session.commit()

    count1 = rebuild_segments_for_raw_events(db_session, ids)
    count2 = rebuild_segments_for_raw_events(db_session, ids)
    assert count1 == 2
    assert count2 == 2
    assert db_session.query(ActivitySegment).count() == 2


def test_rebuild_segments_metadata(db_session, clockify_entries):
    now = datetime.now(timezone.utc)
    entry = clockify_entries[0]
    started, ended = entry_times_from_payload(entry)
    raw = RawEvent(
        source="clockify",
        external_id=entry["id"],
        started_at=started,
        ended_at=ended,
        payload=entry,
        ingested_at=now,
    )
    db_session.add(raw)
    db_session.commit()
    rebuild_segments_for_raw_events(db_session, [raw.id])
    seg = db_session.query(ActivitySegment).one()
    assert seg.activity_type_slug == "work"
    assert seg.metadata_["project"] == "Time Tracker"
    assert (seg.ended_at - seg.started_at).total_seconds() == 4 * 3600
