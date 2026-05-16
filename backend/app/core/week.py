from datetime import date, timedelta


def week_dates_sunday_first(year: int, week: int) -> list[date]:
    """Seven dates Sun–Sat for the calendar week tied to ISO week id YYYY-Www."""
    jan4 = date(year, 1, 4)
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    monday = week1_monday + timedelta(weeks=week - 1)
    sunday = monday - timedelta(days=1)
    return [sunday + timedelta(days=i) for i in range(7)]
