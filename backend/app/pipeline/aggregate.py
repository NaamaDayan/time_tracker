from datetime import datetime, timezone
from typing import Any

from app.pipeline.overlap import load_overlap_priority, winner_for_instant
from app.pipeline.time_budget import day_budget_seconds


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
    timezone_name: str = "UTC",
) -> dict[str, Any]:
    """
    segments: list of dicts with keys started_at, ended_at, activity_type (slug), activity_label, color
    Returns seconds per activity after overlap resolution; percents use 24h * calendar days budget.
    """
    window_start = _ensure_utc(window_start)
    window_end = _ensure_utc(window_end)
    calendar_days, budget_seconds = day_budget_seconds(
        window_start, window_end, timezone_name=timezone_name
    )
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
            "calendar_days": calendar_days,
            "total_seconds": budget_seconds,
            "slices": [],
            "unattributed_seconds": budget_seconds,
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

    attributed_seconds = sum(totals.values())
    slices = [
        {
            "activity_type": slug,
            "label": labels.get(slug, slug),
            "color": colors.get(slug, "#6366f1"),
            "seconds": seconds,
            "percent": round(100.0 * seconds / budget_seconds, 2) if budget_seconds else 0,
        }
        for slug, seconds in sorted(totals.items(), key=lambda x: -x[1])
    ]

    return {
        "calendar_days": calendar_days,
        "total_seconds": budget_seconds,
        "slices": slices,
        "unattributed_seconds": max(0.0, budget_seconds - attributed_seconds),
    }
