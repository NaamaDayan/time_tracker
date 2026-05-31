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


def _default_ranks(**overrides: int) -> dict[str, int]:
    from app.seed_activity_type_priority import DEFAULT_PRIORITY

    ranks = {slug: i for i, slug in enumerate(DEFAULT_PRIORITY, start=1)}
    ranks.update(overrides)
    return ranks


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
        priority_ranks={"read": 1, "sport": 5},
    )
    by_type = {s["activity_type"]: s["seconds"] for s in result["slices"]}
    assert by_type["read"] == 30 * 60
    assert by_type["sport"] == 30 * 60
    assert result["total_seconds"] == 24 * 60 * 60
    assert result["unattributed_seconds"] == 24 * 60 * 60 - 60 * 60
    attributed_pct = sum(s["percent"] for s in result["slices"])
    unattributed_pct = 100.0 * result["unattributed_seconds"] / result["total_seconds"]
    assert abs(attributed_pct + unattributed_pct - 100.0) < 0.1


def test_overlap_db_priority_wins():
    """Higher priority (lower rank) wins overlapping instants."""
    window_start = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 5, 16, 11, 0, tzinfo=timezone.utc)
    segments = [
        _seg("work", "2026-05-16T10:00:00Z", "2026-05-16T11:00:00Z"),
        _seg("sport", "2026-05-16T10:00:00Z", "2026-05-16T11:00:00Z"),
    ]
    result = aggregate_segments(
        segments,
        window_start=window_start,
        window_end=window_end,
        priority_ranks=_default_ranks(),
    )
    by_type = {s["activity_type"]: s["seconds"] for s in result["slices"]}
    assert by_type.get("sport") == 60 * 60
    assert "work" not in by_type


def test_slices_plus_unattributed_equals_100_percent():
    window_start = datetime(2026, 5, 16, 8, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 5, 17, 8, 0, tzinfo=timezone.utc)
    segments = [
        _seg("work", "2026-05-16T09:00:00Z", "2026-05-16T12:00:00Z"),
        _seg("sport", "2026-05-16T14:00:00Z", "2026-05-16T15:00:00Z"),
    ]
    result = aggregate_segments(
        segments,
        window_start=window_start,
        window_end=window_end,
        priority_ranks=_default_ranks(),
    )
    attributed = sum(s["seconds"] for s in result["slices"])
    total = result["total_seconds"]
    assert abs(attributed + result["unattributed_seconds"] - total) < 0.01
    attributed_pct = sum(s["percent"] for s in result["slices"])
    unattributed_pct = 100.0 * result["unattributed_seconds"] / total
    assert abs(attributed_pct + unattributed_pct - 100.0) < 0.1


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
        priority_ranks=_default_ranks(),
    )
    assert result["slices"] == []
    assert result["total_seconds"] == 24 * 60 * 60
    assert result["unattributed_seconds"] == 24 * 60 * 60
