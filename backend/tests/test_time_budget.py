from datetime import datetime, timezone

from app.pipeline.time_budget import calendar_days_in_range, day_budget_seconds

UTC = timezone.utc


def test_single_calendar_day():
    start = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    end = datetime(2026, 5, 16, 22, 0, tzinfo=UTC)
    days, budget = day_budget_seconds(start, end, timezone_name="UTC")
    assert days == 1
    assert budget == 24 * 60 * 60


def test_multi_calendar_days_inclusive():
    start = datetime(2026, 5, 16, 0, 0, tzinfo=UTC)
    end = datetime(2026, 5, 18, 23, 59, tzinfo=UTC)
    assert calendar_days_in_range(start, end, timezone_name="UTC") == 3
