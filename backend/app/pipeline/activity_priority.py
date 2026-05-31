"""Cached lookup for activity type overlap priority (pie chart winner)."""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.models.activity_type_priority import ActivityTypePriority

_CACHE_TTL_SECONDS = 300.0
_cache: tuple[float, dict[str, int]] | None = None


def invalidate_activity_priority_cache() -> None:
    global _cache
    _cache = None


def get_priority_ranks(db: Session) -> dict[str, int]:
    """Return slug → rank map; lower rank = higher priority. 300s in-memory cache."""
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < _CACHE_TTL_SECONDS:
        return _cache[1]

    rows = db.query(ActivityTypePriority).all()
    ranks = {row.activity_type_slug: row.rank for row in rows}
    _cache = (now, ranks)
    return ranks
