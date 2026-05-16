from datetime import datetime, timezone

from app.pipeline.aggregate import aggregate_segments


def _seg(slug: str, start: str, end: str, label: str | None = None):
    return {
        "started_at": datetime.fromisoformat(start.replace("Z", "+00:00")),
        "ended_at": datetime.fromisoformat(end.replace("Z", "+00:00")),
        "activity_type": slug,
        "activity_label": label or slug,
        "color": "#000",
    }


def test_overlap_read_wins_over_sport():
    window_start = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 5, 16, 11, 0, tzinfo=timezone.utc)
    segments = [
        _seg("sport", "2026-05-16T10:00:00Z", "2026-05-16T11:00:00Z"),
        _seg("read", "2026-05-16T10:15:00Z", "2026-05-16T10:45:00Z"),
    ]
    result = aggregate_segments(
        segments,
        window_start=window_start,
        window_end=window_end,
    )
    by_type = {s["activity_type"]: s["seconds"] for s in result["slices"]}
    assert by_type["read"] == 30 * 60
    assert by_type["sport"] == 30 * 60  # 15 min before + 15 min after read


def test_filter_activity_types():
    window_start = datetime(2026, 5, 16, 8, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
    segments = [
        _seg("work", "2026-05-16T08:00:00Z", "2026-05-16T10:00:00Z"),
    ]
    result = aggregate_segments(
        segments,
        window_start=window_start,
        window_end=window_end,
        activity_types=["read"],
    )
    assert result["slices"] == []
    assert result["total_seconds"] == 0
