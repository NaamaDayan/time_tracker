"""DB operations: invalidate overlapping windows and persist merged results."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ActivitySegment, ActivityWindow, ActivityWindowSegment
from app.pipeline.windows.merge import (
    MergedWindow,
    merge_segments_by_type,
    segment_input_from_row,
)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _gap_timedelta() -> timedelta:
    return timedelta(minutes=get_settings().activity_merge_gap_minutes)


def _delete_windows_in_range(
    db: Session,
    *,
    activity_type_slug: str,
    from_: datetime,
    to: datetime,
) -> int:
    """Delete windows of one type that overlap [from_, to]. Returns count deleted."""
    from_ = _ensure_utc(from_)
    to = _ensure_utc(to)
    q = (
        db.query(ActivityWindow)
        .filter(
            ActivityWindow.activity_type_slug == activity_type_slug,
            ActivityWindow.started_at < to,
            ActivityWindow.ended_at > from_,
        )
    )
    ids = [w.id for w in q.all()]
    if not ids:
        return 0
    db.execute(delete(ActivityWindow).where(ActivityWindow.id.in_(ids)))
    db.flush()
    return len(ids)


def _load_segments_for_type_in_range(
    db: Session,
    *,
    activity_type_slug: str,
    from_: datetime,
    to: datetime,
) -> list[ActivitySegment]:
    from_ = _ensure_utc(from_)
    to = _ensure_utc(to)
    return (
        db.query(ActivitySegment)
        .filter(
            ActivitySegment.activity_type_slug == activity_type_slug,
            ActivitySegment.started_at < to,
            ActivitySegment.ended_at > from_,
        )
        .order_by(ActivitySegment.started_at, ActivitySegment.id)
        .all()
    )


def _persist_windows(
    db: Session,
    merged: list[MergedWindow],
    *,
    gap_minutes: int,
) -> int:
    if not merged:
        return 0

    now = datetime.now(timezone.utc)
    metadata_snapshot = {"merge_gap_minutes": gap_minutes}

    for win in merged:
        window = ActivityWindow(
            activity_type_slug=win.activity_type_slug,
            started_at=_ensure_utc(win.started_at),
            ended_at=_ensure_utc(win.ended_at),
            confidence=win.confidence,
            sources=sorted(win.sources),
            segment_count=len(win.segment_ids),
            computed_at=now,
            metadata_=metadata_snapshot,
        )
        db.add(window)
        db.flush()
        for seg_id in win.segment_ids:
            db.add(ActivityWindowSegment(window_id=window.id, segment_id=seg_id))

    return len(merged)


def recompute_type_in_range(
    db: Session,
    *,
    activity_type_slug: str,
    from_: datetime,
    to: datetime,
) -> int:
    """
    Delete and rebuild windows for one activity type in [from_, to] (padded bounds
    should be applied by the caller).
    """
    gap = _gap_timedelta()
    gap_minutes = get_settings().activity_merge_gap_minutes
    from_ = _ensure_utc(from_)
    to = _ensure_utc(to)

    _delete_windows_in_range(
        db, activity_type_slug=activity_type_slug, from_=from_, to=to
    )

    segments = _load_segments_for_type_in_range(
        db, activity_type_slug=activity_type_slug, from_=from_, to=to
    )
    inputs = [segment_input_from_row(s) for s in segments]
    merged = merge_segments_by_type(
        inputs, activity_type_slugs={activity_type_slug}, gap_minutes=gap_minutes
    )
    written = _persist_windows(db, merged, gap_minutes=gap_minutes)
    return written


def recompute_types_in_range(
    db: Session,
    *,
    activity_type_slugs: set[str],
    bounds_by_type: dict[str, tuple[datetime, datetime]],
) -> int:
    """Recompute each activity type using its padded (from_, to) bounds."""
    total = 0
    for slug in activity_type_slugs:
        from_, to = bounds_by_type[slug]
        total += recompute_type_in_range(
            db, activity_type_slug=slug, from_=from_, to=to
        )
    return total


def compute_padded_bounds(
    segments: list[ActivitySegment],
) -> dict[str, tuple[datetime, datetime]]:
    """Per activity type: min(start) - gap, max(end) + gap."""
    gap = _gap_timedelta()
    bounds: dict[str, tuple[datetime, datetime]] = {}
    for seg in segments:
        slug = seg.activity_type_slug
        start = _ensure_utc(seg.started_at)
        end = _ensure_utc(seg.ended_at)
        if slug not in bounds:
            bounds[slug] = (start - gap, end + gap)
        else:
            lo, hi = bounds[slug]
            bounds[slug] = (min(lo, start - gap), max(hi, end + gap))
    return bounds


def delete_all_windows(db: Session) -> None:
    db.execute(delete(ActivityWindowSegment))
    db.execute(delete(ActivityWindow))
    db.flush()
