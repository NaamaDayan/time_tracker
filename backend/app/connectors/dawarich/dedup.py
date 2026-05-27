from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import ActivitySegment

GEOFENCE_SOURCE = "geofence"
OVERLAP_RATIO_THRESHOLD = 0.7


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _interval_seconds(start: datetime, end: datetime) -> float:
    return max(0.0, (_ensure_utc(end) - _ensure_utc(start)).total_seconds())


def _overlap_seconds(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    start = max(_ensure_utc(a_start), _ensure_utc(b_start))
    end = min(_ensure_utc(a_end), _ensure_utc(b_end))
    return _interval_seconds(start, end)


def _normalize_place_name(name: str | None) -> str:
    return (name or "").strip().lower()


def geofence_covers_visit(
    db: Session,
    *,
    visit_start: datetime,
    visit_end: datetime,
    place_name: str | None,
) -> ActivitySegment | None:
    """Return overlapping geofence segment if it should supersede a Dawarich visit."""
    if visit_end <= visit_start:
        return None

    visit_dur = _interval_seconds(visit_start, visit_end)
    if visit_dur <= 0:
        return None

    place_norm = _normalize_place_name(place_name)
    candidates = (
        db.query(ActivitySegment)
        .filter(
            ActivitySegment.source == GEOFENCE_SOURCE,
            ActivitySegment.ended_at.isnot(None),
            ActivitySegment.started_at < visit_end,
            ActivitySegment.ended_at > visit_start,
        )
        .all()
    )

    for seg in candidates:
        if seg.ended_at is None:
            continue
        overlap = _overlap_seconds(
            visit_start, visit_end, seg.started_at, seg.ended_at
        )
        shorter = min(visit_dur, _interval_seconds(seg.started_at, seg.ended_at))
        if shorter <= 0 or overlap / shorter < OVERLAP_RATIO_THRESHOLD:
            continue
        zone = _normalize_place_name((seg.metadata_ or {}).get("zone_name"))
        if zone and place_norm and zone in place_norm:
            return seg
        if zone and place_norm and place_norm in zone:
            return seg
    return None
