"""Public entry points for window aggregation."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ActivitySegment
from app.pipeline.windows.recompute import (
    compute_padded_bounds,
    delete_all_windows,
    recompute_type_in_range,
    recompute_types_in_range,
)


def recompute_windows_for_segments(db: Session, segment_ids: list[int]) -> int:
    """
    Incrementally rebuild windows affected by changed segments.

    Loads segments by id, computes padded bounds per activity type, deletes
    overlapping windows, and re-merges segments in those ranges.
    """
    if not segment_ids:
        return 0

    segments = (
        db.query(ActivitySegment).filter(ActivitySegment.id.in_(segment_ids)).all()
    )
    if not segments:
        return 0

    segments_for_bounds = [
        s for s in segments if not (s.metadata_ or {}).get("exclude_from_windows")
    ]
    if not segments_for_bounds:
        return 0

    bounds = compute_padded_bounds(segments_for_bounds, db)
    written = recompute_types_in_range(
        db,
        activity_type_slugs=set(bounds.keys()),
        bounds_by_type=bounds,
    )
    db.commit()
    return written


def recompute_windows_for_range(
    db: Session,
    *,
    activity_type_slugs: set[str],
    from_: datetime,
    to: datetime,
) -> int:
    """Rebuild windows for explicit types and time range (caller supplies bounds)."""
    if not activity_type_slugs:
        return 0

    bounds = {slug: (from_, to) for slug in activity_type_slugs}
    written = recompute_types_in_range(
        db, activity_type_slugs=activity_type_slugs, bounds_by_type=bounds
    )
    db.commit()
    return written


def recompute_windows_after_segment_change(
    db: Session,
    *,
    segment_ids: list[int] | None = None,
    extra_types: set[str] | None = None,
    bounds_from_segments: list[ActivitySegment] | None = None,
) -> int:
    """
    Recompute without committing (for use inside larger transactions).

    Used when segment_ids may be empty but extra_types/bounds_from_segments
    describe invalidation (e.g. type change or delete).
    """
    segments: list[ActivitySegment] = []
    if segment_ids:
        segments.extend(
            db.query(ActivitySegment).filter(ActivitySegment.id.in_(segment_ids)).all()
        )
    if bounds_from_segments:
        segments.extend(bounds_from_segments)

    type_slugs: set[str] = set(extra_types or [])
    for seg in segments:
        type_slugs.add(seg.activity_type_slug)

    if not type_slugs:
        return 0

    bounds = compute_padded_bounds(segments, db) if segments else {}
    gap = get_settings().activity_merge_gap_minutes
    from datetime import timedelta

    pad = timedelta(minutes=gap)
    now = datetime.now(timezone.utc)
    default_lo = now - pad
    default_hi = now + pad
    for slug in type_slugs:
        if slug not in bounds:
            bounds[slug] = (default_lo, default_hi)

    return recompute_types_in_range(
        db, activity_type_slugs=type_slugs, bounds_by_type=bounds
    )


def backfill_all_windows(
    db: Session,
    *,
    from_: datetime | None = None,
    to: datetime | None = None,
) -> int:
    """Rebuild all windows from segments. Optional from_/to limit segment query.

    Truncates existing windows first.
    """
    delete_all_windows(db)

    q = db.query(ActivitySegment)
    if from_ is not None:
        q = q.filter(ActivitySegment.ended_at > from_)
    if to is not None:
        q = q.filter(ActivitySegment.started_at < to)

    segments = q.order_by(ActivitySegment.started_at).all()
    if not segments:
        db.commit()
        return 0

    type_slugs = {s.activity_type_slug for s in segments}
    if from_ is None or to is None:
        bounds = compute_padded_bounds(segments, db)
    else:
        bounds = {slug: (from_, to) for slug in type_slugs}

    written = recompute_types_in_range(
        db, activity_type_slugs=type_slugs, bounds_by_type=bounds
    )
    db.commit()
    return written
