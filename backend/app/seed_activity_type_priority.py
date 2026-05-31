"""Seed default activity type priority when the table is empty."""

from sqlalchemy.orm import Session

from app.models.activity_type_priority import ActivityTypePriority

DEFAULT_PRIORITY: list[str] = [
    "sleep",
    "sport",
    "work",
    "family",
    "fun",
    "meal_prep",
    "watching_tv",
    "bedroom",
    "bathroom",
    "consuming",
    "communication",
    "music",
    "podcasts",
    "transport",
]


def seed_activity_type_priority(db: Session) -> int:
    """Insert default ranks if the table is empty. Returns rows inserted."""
    if db.query(ActivityTypePriority).count() > 0:
        return 0
    for rank, slug in enumerate(DEFAULT_PRIORITY, start=1):
        db.add(ActivityTypePriority(activity_type_slug=slug, rank=rank))
    db.commit()
    return len(DEFAULT_PRIORITY)
