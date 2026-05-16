from datetime import datetime, timezone

from app.models import RawEvent
from app.pipeline.habits import compute_habits_for_week
from app.pipeline.normalize import entry_times_from_payload, rebuild_segments_for_raw_events


def _add_work_segment(db_session, start: str, end: str, external_id: str):
    entry = {
        "id": external_id,
        "timeInterval": {"start": start, "end": end},
        "project": {"name": "Work"},
    }
    started, ended = entry_times_from_payload(entry)
    raw = RawEvent(
        source="clockify",
        external_id=external_id,
        started_at=started,
        ended_at=ended,
        payload=entry,
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(raw)
    db_session.flush()
    rebuild_segments_for_raw_events(db_session, [raw.id])


def test_weekday_work_target_partial_score(db_session):
    # Monday 2026-05-11 — 4h work (below 6h target)
    _add_work_segment(db_session, "2026-05-11T06:00:00Z", "2026-05-11T10:00:00Z", "w1")
    results = compute_habits_for_week(db_session, 2026, 20)
    weekday = next(g for g in results if g["slug"] == "weekday_work_target")
    monday = next(d for d in weekday["daily"] if d["date"] == "2026-05-11")
    assert monday["score"] is not None
    assert 0.5 < monday["score"] < 0.7  # ~4/6 hours
