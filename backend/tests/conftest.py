import json
from pathlib import Path

import pytest
from sqlalchemy import JSON, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import ActivityType, HabitGoal, SourceAccount  # noqa: F401
from app.models.window import ActivityWindow, ActivityWindowSegment  # noqa: F401


def _patch_jsonb_for_sqlite():
    """Replace JSONB columns with JSON when using SQLite in tests."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@pytest.fixture
def db_session():
    _patch_jsonb_for_sqlite()
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

    session.add(ActivityType(slug="work", label="Work", color="#3b82f6"))
    session.add(ActivityType(slug="screen_time", label="Screen time", color="#8b5cf6"))
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
    session.add(SourceAccount(source="clockify", display_name="Clockify", is_active=True))
    session.commit()

    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def clockify_entries():
    path = Path(__file__).parent / "fixtures" / "clockify_time_entries.json"
    return json.loads(path.read_text())
