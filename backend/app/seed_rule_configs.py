"""Seed default activity rule configs when the table is empty."""

from typing import Any

from sqlalchemy.orm import Session

from app.models.activity_rule_config import ActivityRuleConfig

DEFAULT_RULE_CONFIGS: list[dict[str, Any]] = [
    {
        "activity_type_slug": "sleep",
        "enabled": True,
        "min_duration_minutes": 180,
        "merge_gap_minutes": 45,
        "boost_signals": {"watch_confirmed": True},
        "custom_params": {"fallback_screen_off_hours": [20, 10]},
    },
    {
        "activity_type_slug": "work",
        "enabled": True,
        "min_duration_minutes": 20,
        "merge_gap_minutes": 30,
        "boost_signals": {},
        "custom_params": {
            "work_days": [0, 1, 2, 3, 6],
            "work_hours_start": 8,
            "work_hours_end": 20,
        },
    },
    {
        "activity_type_slug": "fun",
        "enabled": True,
        "min_duration_minutes": 45,
        "merge_gap_minutes": 60,
        "boost_signals": {},
        "custom_params": {},
    },
    {
        "activity_type_slug": "family",
        "enabled": True,
        "min_duration_minutes": 30,
        "merge_gap_minutes": 60,
        "boost_signals": {},
        "custom_params": {},
    },
    {
        "activity_type_slug": "sport",
        "enabled": True,
        "min_duration_minutes": 20,
        "merge_gap_minutes": 15,
        "boost_signals": {"watch_active": True, "hevy_open": True},
        "custom_params": {},
    },
    {
        "activity_type_slug": "meal_prep",
        "enabled": True,
        "min_duration_minutes": 10,
        "merge_gap_minutes": 10,
        "boost_signals": {},
        "custom_params": {},
    },
    {
        "activity_type_slug": "bathroom",
        "enabled": True,
        "min_duration_minutes": 2,
        "merge_gap_minutes": 5,
        "boost_signals": {},
        "custom_params": {"max_duration_minutes": 15},
    },
    {
        "activity_type_slug": "bedroom",
        "enabled": True,
        "min_duration_minutes": 10,
        "merge_gap_minutes": 10,
        "boost_signals": {},
        "custom_params": {},
    },
    {
        "activity_type_slug": "watching_tv",
        "enabled": True,
        "min_duration_minutes": 20,
        "merge_gap_minutes": 15,
        "boost_signals": {},
        "custom_params": {},
    },
    {
        "activity_type_slug": "consuming",
        "enabled": True,
        "min_duration_minutes": 5,
        "merge_gap_minutes": 5,
        "boost_signals": {},
        "custom_params": {},
    },
    {
        "activity_type_slug": "music",
        "enabled": True,
        "min_duration_minutes": 1,
        "merge_gap_minutes": 5,
        "boost_signals": {},
        "custom_params": {},
    },
    {
        "activity_type_slug": "podcasts",
        "enabled": True,
        "min_duration_minutes": 1,
        "merge_gap_minutes": 5,
        "boost_signals": {},
        "custom_params": {},
    },
    {
        "activity_type_slug": "communication",
        "enabled": True,
        "min_duration_minutes": 3,
        "merge_gap_minutes": 5,
        "boost_signals": {},
        "custom_params": {},
    },
    {
        "activity_type_slug": "transport",
        "enabled": True,
        "min_duration_minutes": 5,
        "merge_gap_minutes": 10,
        "boost_signals": {},
        "custom_params": {},
    },
]


def seed_rule_configs(db: Session) -> int:
    """Insert default configs if the table is empty. Returns rows inserted."""
    if db.query(ActivityRuleConfig).count() > 0:
        return 0
    for row in DEFAULT_RULE_CONFIGS:
        db.add(ActivityRuleConfig(**row))
    db.commit()
    return len(DEFAULT_RULE_CONFIGS)
