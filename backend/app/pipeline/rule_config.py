"""Cached lookup for per-activity-type rule configuration."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.activity_rule_config import ActivityRuleConfig

_CACHE_TTL_SECONDS = 60.0
_cache: dict[str, tuple[float, ActivityRuleConfig]] = {}
_all_cache: tuple[float, list[ActivityRuleConfig]] | None = None


@dataclass(frozen=True)
class RuleConfigDefaults:
    enabled: bool = True
    min_duration_minutes: int = 5
    merge_gap_minutes: int | None = None
    boost_signals: dict[str, Any] | None = None
    custom_params: dict[str, Any] | None = None


def invalidate_rule_config_cache() -> None:
    global _all_cache
    _cache.clear()
    _all_cache = None


def _global_merge_gap_minutes() -> int:
    return get_settings().activity_merge_gap_minutes


def get_rule_config(slug: str, db: Session) -> ActivityRuleConfig:
    """Return config for slug, with 60s in-memory cache."""
    now = time.monotonic()
    cached = _cache.get(slug)
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    row = (
        db.query(ActivityRuleConfig)
        .filter(ActivityRuleConfig.activity_type_slug == slug)
        .first()
    )
    if row is None:
        row = ActivityRuleConfig(
            activity_type_slug=slug,
            enabled=True,
            min_duration_minutes=5,
            merge_gap_minutes=_global_merge_gap_minutes(),
            boost_signals={},
            custom_params={},
        )
    _cache[slug] = (now, row)
    return row


def get_merge_gap_minutes(slug: str, db: Session) -> int:
    cfg = get_rule_config(slug, db)
    if cfg.merge_gap_minutes is not None:
        return int(cfg.merge_gap_minutes)
    return _global_merge_gap_minutes()


def get_all_rule_configs(db: Session) -> list[ActivityRuleConfig]:
    global _all_cache
    now = time.monotonic()
    if _all_cache is not None and now - _all_cache[0] < _CACHE_TTL_SECONDS:
        return _all_cache[1]

    rows = (
        db.query(ActivityRuleConfig)
        .order_by(ActivityRuleConfig.activity_type_slug)
        .all()
    )
    for row in rows:
        _cache[row.activity_type_slug] = (now, row)
    _all_cache = (now, rows)
    return rows
