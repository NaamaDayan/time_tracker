"""Net (additive) totals per activity type — overlaps double-count."""

from datetime import datetime, timezone
from typing import Any

from app.pipeline.aggregate import _clip_segment, _ensure_utc


def net_totals_segments(
    segments: list[dict[str, Any]],
    *,
    window_start: datetime,
    window_end: datetime,
    activity_types: list[str] | None = None,
) -> dict[str, Any]:
    """
    Sum clipped segment durations per activity type without overlap resolution.
    """
    window_start = _ensure_utc(window_start)
    window_end = _ensure_utc(window_end)
    allowed = set(activity_types) if activity_types else None

    totals: dict[str, float] = {}
    labels: dict[str, str] = {}
    colors: dict[str, str] = {}

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
        duration = (bounds[1] - bounds[0]).total_seconds()
        totals[slug] = totals.get(slug, 0.0) + duration
        labels[slug] = seg.get("activity_label", slug)
        colors[slug] = seg.get("color", "#6366f1")

    total_seconds = sum(totals.values())
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
    }
