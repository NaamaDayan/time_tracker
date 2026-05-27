from datetime import datetime, timedelta, timezone

from app.pipeline.windows.merge import SegmentInput, merge_segments, merge_segments_by_type

UTC = timezone.utc


def _seg(
    id: int,
    start: datetime,
    end: datetime,
    *,
    slug: str = "work",
    source: str = "activitywatch_desktop",
) -> SegmentInput:
    return SegmentInput(
        id=id,
        activity_type_slug=slug,
        started_at=start,
        ended_at=end,
        source=source,
    )


def test_merge_small_gap():
    base = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    segments = [
        _seg(1, base, base + timedelta(minutes=20)),
        _seg(2, base + timedelta(minutes=21), base + timedelta(hours=1)),
    ]
    windows = merge_segments(segments, activity_type_slug="work", gap_minutes=5)
    assert len(windows) == 1
    assert windows[0].started_at == base
    assert windows[0].ended_at == base + timedelta(hours=1)
    assert windows[0].segment_ids == [1, 2]


def test_no_merge_gap_exceeds_threshold():
    base = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    segments = [
        _seg(1, base, base + timedelta(minutes=20)),
        _seg(2, base + timedelta(minutes=26), base + timedelta(hours=1)),
    ]
    windows = merge_segments(segments, activity_type_slug="work", gap_minutes=5)
    assert len(windows) == 2


def test_merge_at_exact_threshold():
    base = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    end1 = base + timedelta(minutes=20)
    start2 = end1 + timedelta(minutes=5)
    segments = [
        _seg(1, base, end1),
        _seg(2, start2, base + timedelta(hours=1)),
    ]
    windows = merge_segments(segments, activity_type_slug="work", gap_minutes=5)
    assert len(windows) == 1


def test_chain_merge_transitive():
    base = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    segments = [
        _seg(1, base, base + timedelta(minutes=10)),
        _seg(2, base + timedelta(minutes=14), base + timedelta(minutes=24)),
        _seg(3, base + timedelta(minutes=28), base + timedelta(minutes=50)),
    ]
    windows = merge_segments(segments, activity_type_slug="work", gap_minutes=5)
    assert len(windows) == 1
    assert windows[0].segment_ids == [1, 2, 3]


def test_no_cross_type_merge():
    base = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    segments = [
        _seg(1, base, base + timedelta(minutes=30), slug="work"),
        _seg(2, base + timedelta(minutes=31), base + timedelta(hours=1), slug="read"),
    ]
    windows = merge_segments_by_type(segments, gap_minutes=5)
    assert len(windows) == 2
    slugs = {w.activity_type_slug for w in windows}
    assert slugs == {"work", "read"}


def test_overlap_union():
    base = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    segments = [
        _seg(1, base, base + timedelta(minutes=30)),
        _seg(2, base + timedelta(minutes=15), base + timedelta(minutes=45)),
    ]
    windows = merge_segments(segments, activity_type_slug="work", gap_minutes=5)
    assert len(windows) == 1
    assert windows[0].started_at == base
    assert windows[0].ended_at == base + timedelta(minutes=45)


def test_cross_source_merge():
    base = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    segments = [
        _seg(1, base, base + timedelta(minutes=20), source="activitywatch_desktop"),
        _seg(2, base + timedelta(minutes=21), base + timedelta(hours=1), source="google_calendar"),
    ]
    windows = merge_segments(segments, activity_type_slug="work", gap_minutes=5)
    assert len(windows) == 1
    assert set(windows[0].sources) == {"activitywatch_desktop", "google_calendar"}


def test_empty_input():
    assert merge_segments([], activity_type_slug="work", gap_minutes=5) == []
