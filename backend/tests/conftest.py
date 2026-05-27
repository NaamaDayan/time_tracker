import pytest
from sqlalchemy import JSON, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (  # noqa: F401
    ActivityRuleConfig,
    ActivityType,
    GpsZone,
    HabitGoal,
    SourceAccount,
)
from app.seed_rule_configs import seed_rule_configs
from app.models.window import ActivityWindow, ActivityWindowSegment  # noqa: F401


def _patch_pg_types_for_sqlite():
    """Replace PostgreSQL-specific column types for SQLite in tests."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@pytest.fixture
def db_session():
    _patch_pg_types_for_sqlite()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    session.add(ActivityType(slug="sleep", label="Sleep", color="#6366f1"))
    session.add(ActivityType(slug="work", label="Work", color="#3b82f6"))
    session.add(ActivityType(slug="sport", label="Sport", color="#22c55e"))
    session.add(ActivityType(slug="fun", label="Fun", color="#ec4899"))
    session.add(ActivityType(slug="family", label="Family", color="#f472b6"))
    session.add(ActivityType(slug="meal_prep", label="Meal prep", color="#fb923c"))
    session.add(ActivityType(slug="bathroom", label="Bathroom", color="#94a3b8"))
    session.add(ActivityType(slug="bedroom", label="Bedroom", color="#a78bfa"))
    session.add(ActivityType(slug="watching_tv", label="Watching TV", color="#818cf8"))
    session.add(ActivityType(slug="music", label="Music", color="#84cc16"))
    session.add(ActivityType(slug="podcasts", label="Podcasts", color="#65a30d"))
    session.add(ActivityType(slug="transport", label="Transport", color="#6b7280"))
    session.add(ActivityType(slug="screen_time", label="Screen time", color="#8b5cf6"))
    session.add(ActivityType(slug="communication", label="Communication", color="#f59e0b"))
    session.add(ActivityType(slug="music_podcast", label="Music / Podcast", color="#84cc16"))
    session.add(ActivityType(slug="consuming", label="Consuming", color="#ef4444"))
    session.add(ActivityType(slug="read", label="Read", color="#10b981"))
    session.add(ActivityType(slug="phone_usage", label="Phone Usage", color="#64748b"))
    session.add(
        HabitGoal(
            slug="weekday_work_target",
            name="Weekday work (6h+)",
            rule_json={
                "type": "daily_duration",
                "activity": "work",
                "min_seconds": 21600,
                "days": [0, 1, 2, 3, 4],
            },
            is_active=True,
        )
    )
    session.add(SourceAccount(source="activitywatch_desktop", display_name="ActivityWatch Desktop", is_active=True))
    session.commit()
    seed_rule_configs(session)
    from app.pipeline.rule_config import invalidate_rule_config_cache

    invalidate_rule_config_cache()

    yield session
    session.close()
    Base.metadata.drop_all(engine)
