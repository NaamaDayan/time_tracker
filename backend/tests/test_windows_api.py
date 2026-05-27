from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import ActivitySegment
from app.pipeline.windows.service import backfill_all_windows

UTC = timezone.utc


@pytest.fixture
def client(db_session, monkeypatch):
    from app.config import get_settings
    from app.database import get_db

    monkeypatch.setenv("API_KEY", "test-key")
    get_settings.cache_clear()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, headers={"X-API-Key": "test-key"})
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_get_windows(client, db_session):
    base = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    db_session.add(
        ActivitySegment(
            started_at=base,
            ended_at=base + timedelta(minutes=20),
            activity_type_slug="work",
            source="manual",
            confidence=1.0,
        )
    )
    db_session.add(
        ActivitySegment(
            started_at=base + timedelta(minutes=21),
            ended_at=base + timedelta(hours=1),
            activity_type_slug="work",
            source="manual",
            confidence=1.0,
        )
    )
    db_session.commit()
    backfill_all_windows(db_session)

    from_ = base.isoformat()
    to = (base + timedelta(days=1)).isoformat()
    r = client.get("/api/v1/windows", params={"from": from_, "to": to})
    assert r.status_code == 200
    data = r.json()
    assert len(data["windows"]) == 1
    assert len(data["windows"][0]["segment_ids"]) == 2


def test_get_windows_hides_shorter_than_merge_gap(client, db_session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("ACTIVITY_MERGE_GAP_MINUTES", "5")
    get_settings.cache_clear()

    base = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    db_session.add(
        ActivitySegment(
            started_at=base,
            ended_at=base + timedelta(minutes=2),
            activity_type_slug="work",
            source="manual",
            confidence=1.0,
        )
    )
    db_session.commit()
    backfill_all_windows(db_session)

    from_ = base.isoformat()
    to = (base + timedelta(days=1)).isoformat()
    r = client.get("/api/v1/windows", params={"from": from_, "to": to})
    assert r.status_code == 200
    assert r.json()["windows"] == []

    get_settings.cache_clear()
