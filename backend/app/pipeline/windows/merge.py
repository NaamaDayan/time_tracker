"""
Pure gap-merge algorithm for activity windows.

Merges segments of the same activity_type when the gap between consecutive
intervals is <= threshold, or when intervals overlap (union).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class SegmentInput:
    """Minimal segment shape for merge (DB-agnostic)."""

    id: int
    activity_type_slug: str
    started_at: datetime
    ended_at: datetime
    source: str
    confidence: float = 1.0
    user_confirmed: bool = False


@dataclass
class MergedWindow:
    activity_type_slug: str
    started_at: datetime
    ended_at: datetime
    segment_ids: list[int] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    confidence: float = 1.0
    confirmed_by_user: bool = False


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _should_merge(
    current: MergedWindow,
    nxt: SegmentInput,
    *,
    gap_threshold: timedelta,
) -> bool:
    """Merge if overlapping or gap between current end and next start is within threshold."""
    gap = _ensure_utc(nxt.started_at) - _ensure_utc(current.ended_at)
    if _ensure_utc(nxt.started_at) < _ensure_utc(current.ended_at):
        return True
    return gap <= gap_threshold


def _absorb_segment(current: MergedWindow, seg: SegmentInput) -> None:
    current.ended_at = max(_ensure_utc(current.ended_at), _ensure_utc(seg.ended_at))
    current.started_at = min(_ensure_utc(current.started_at), _ensure_utc(seg.started_at))
    current.segment_ids.append(seg.id)
    if seg.source not in current.sources:
        current.sources.append(seg.source)
    current.confidence = min(current.confidence, seg.confidence)
    current.confirmed_by_user = current.confirmed_by_user or seg.user_confirmed


def _segment_to_window(seg: SegmentInput) -> MergedWindow:
    return MergedWindow(
        activity_type_slug=seg.activity_type_slug,
        started_at=_ensure_utc(seg.started_at),
        ended_at=_ensure_utc(seg.ended_at),
        segment_ids=[seg.id],
        sources=[seg.source],
        confidence=seg.confidence,
        confirmed_by_user=seg.user_confirmed,
    )


def merge_segments(
    segments: list[SegmentInput],
    *,
    activity_type_slug: str,
    gap_minutes: int,
) -> list[MergedWindow]:
    """
    Merge segments of a single activity type by gap threshold and overlap.

    Segments with other activity types are ignored. Input may be unsorted.
    """
    gap_threshold = timedelta(minutes=gap_minutes)
    typed = [s for s in segments if s.activity_type_slug == activity_type_slug]
    if not typed:
        return []

    typed.sort(key=lambda s: (_ensure_utc(s.started_at), s.id))

    windows: list[MergedWindow] = []
    current: MergedWindow | None = None

    for seg in typed:
        if current is None:
            current = _segment_to_window(seg)
            continue
        if _should_merge(current, seg, gap_threshold=gap_threshold):
            _absorb_segment(current, seg)
        else:
            windows.append(current)
            current = _segment_to_window(seg)

    if current is not None:
        windows.append(current)

    return windows


def merge_segments_by_type(
    segments: list[SegmentInput],
    *,
    activity_type_slugs: set[str] | None = None,
    gap_minutes: int,
) -> list[MergedWindow]:
    """Run merge_segments for each activity type present (or requested subset)."""
    if activity_type_slugs is None:
        activity_type_slugs = {s.activity_type_slug for s in segments}
    result: list[MergedWindow] = []
    for slug in sorted(activity_type_slugs):
        result.extend(
            merge_segments(segments, activity_type_slug=slug, gap_minutes=gap_minutes)
        )
    result.sort(key=lambda w: (_ensure_utc(w.started_at), w.activity_type_slug))
    return result


def segment_input_from_row(seg: Any) -> SegmentInput:
    """Build SegmentInput from an ActivitySegment ORM instance."""
    from app.pipeline.confidence import segment_user_confirmed

    meta = seg.metadata_ or {}
    return SegmentInput(
        id=seg.id,
        activity_type_slug=seg.activity_type_slug,
        started_at=seg.started_at,
        ended_at=seg.ended_at,
        source=seg.source,
        confidence=seg.confidence,
        user_confirmed=segment_user_confirmed(meta),
    )
