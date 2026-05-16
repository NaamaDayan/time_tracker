from datetime import datetime, timedelta, timezone
from typing import Any

from app.pipeline.overlap import load_overlap_priority, winner_for_instant


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clip_segment(
    start: datetime,
    end: datetime,
    window_start: datetime,
    window_end: datetime,
) -> tuple[datetime, datetime] | None:
    s = max(_ensure_utc(start), window_start)
    e = min(_ensure_utc(end), window_end)
    if e <= s:
        return None
    return s, e


def aggregate_segments(
    segments: list[dict[str, Any]],
    *,
    window_start: datetime,
    window_end: datetime,
    activity_types: list[str] | None = None,
) -> dict[str, Any]:
    """
    segments: list of dicts with keys started_at, ended_at, activity_type (slug), activity_label, color
    Returns seconds per activity after overlap resolution.
    """
    window_start = _ensure_utc(window_start)
    window_end = _ensure_utc(window_end)
    priority = load_overlap_priority()
    allowed = set(activity_types) if activity_types else None

    clipped: list[tuple[datetime, datetime, str, str, str]] = []
    for seg in segments:
        slug = seg["activity_type"]
        if allowed is not None and slug not in allowed:
            continue
        bounds = _clip_segment(
            seg["started_at"],
            seg["ended_at"],
            window_start,
            window_end,
        )
        if bounds is None:
            continue
        clipped.append(
            (
                bounds[0],
                bounds[1],
                slug,
                seg.get("activity_label", slug),
                seg.get("color", "#6366f1"),
            )
        )

    if not clipped:
        return {
            "total_seconds": 0,
            "slices": [],
            "unattributed_seconds": (window_end - window_start).total_seconds(),
        }

    boundaries: set[datetime] = {window_start, window_end}
    for start, end, _, _, _ in clipped:
        boundaries.add(start)
        boundaries.add(end)
    points = sorted(boundaries)

    totals: dict[str, float] = {}
    labels: dict[str, str] = {}
    colors: dict[str, str] = {}

    for i in range(len(points) - 1):
        t0, t1 = points[i], points[i + 1]
        if t1 <= t0:
            continue
        covering = [
            slug
            for start, end, slug, _, _ in clipped
            if start < t1 and end > t0
        ]
        winner = winner_for_instant(covering, priority)
        if winner is None:
            continue
        duration = (t1 - t0).total_seconds()
        totals[winner] = totals.get(winner, 0.0) + duration
        for start, end, slug, label, color in clipped:
            if slug == winner:
                labels[slug] = label
                colors[slug] = color
                break

    total_seconds = sum(totals.values())
    window_seconds = (window_end - window_start).total_seconds()
    slices = [
        {
            "activity_type": slug,
            "label": labels.get(slug, slug),
            "color": colors.get(slug, "#6366f1"),
            "seconds": seconds,
            "percent": round(100.0 * seconds / total_seconds, 2) if total_seconds else 0,
        }
        for slug, seconds in sorted(totals.items(), key=lambda x: -x[1])
    ]

    return {
        "total_seconds": total_seconds,
        "slices": slices,
        "unattributed_seconds": max(0.0, window_seconds - total_seconds),
    }
