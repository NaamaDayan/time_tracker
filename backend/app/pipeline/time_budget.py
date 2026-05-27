"""Calendar-day time budget helpers for overlap (pie) aggregation."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SECONDS_PER_DAY = 24 * 60 * 60


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def calendar_days_in_range(
    window_start: datetime,
    window_end: datetime,
    *,
    timezone_name: str,
) -> int:
    """Inclusive calendar days between window bounds in the user's timezone."""
    tz = ZoneInfo(timezone_name)
    start_date = _ensure_utc(window_start).astimezone(tz).date()
    end_date = _ensure_utc(window_end).astimezone(tz).date()
    return max(1, (end_date - start_date).days + 1)


def day_budget_seconds(
    window_start: datetime,
    window_end: datetime,
    *,
    timezone_name: str,
) -> tuple[int, float]:
    """Return (calendar_days, seconds) where seconds = days * 24h."""
    days = calendar_days_in_range(
        window_start, window_end, timezone_name=timezone_name
    )
    return days, days * SECONDS_PER_DAY
