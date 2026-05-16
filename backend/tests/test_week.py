from datetime import date

from app.core.week import week_dates_sunday_first


def test_week_dates_sunday_first_starts_on_sunday():
    days = week_dates_sunday_first(2026, 20)
    assert len(days) == 7
    assert days[0].weekday() == 6  # Sunday
    assert days[6].weekday() == 5  # Saturday
    assert days[0] == date(2026, 5, 10)
    assert days[6] == date(2026, 5, 16)
