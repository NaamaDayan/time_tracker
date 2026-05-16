from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import ActivitySegment, ActivityType


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


def test_classify_google_all_day_metadata():
    from app.pipeline.classify import classify_google_calendar_event

    _, meta = classify_google_calendar_event(
        {
            "summary": "Holiday",
            "start": {"date": "2026-05-10"},
            "end": {"date": "2026-05-11"},
        }
    )
    assert meta["is_all_day"] is True


def test_create_update_delete_manual_segment(client, db_session):
    db_session.add(ActivityType(slug="fun", label="Fun", color="#ec4899"))
    db_session.commit()

    create = client.post(
        "/api/v1/segments",
        json={
            "started_at": "2026-05-10T10:00:00Z",
            "ended_at": "2026-05-10T11:00:00Z",
            "activity_type": "fun",
            "title": "Coffee break",
        },
    )
    assert create.status_code == 200
    data = create.json()
    assert data["source"] == "manual"
    assert data["metadata"]["title"] == "Coffee break"
    seg_id = data["id"]

    update = client.patch(
        f"/api/v1/segments/{seg_id}",
        json={"title": "Long coffee", "ended_at": "2026-05-10T12:00:00Z"},
    )
    assert update.status_code == 200
    assert update.json()["metadata"]["title"] == "Long coffee"

    delete = client.delete(f"/api/v1/segments/{seg_id}")
    assert delete.status_code == 204
    assert db_session.get(ActivitySegment, seg_id) is None


def test_cannot_edit_synced_segment(client, db_session):
    seg = ActivitySegment(
        started_at=datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
        activity_type_slug="work",
        source="clockify",
        confidence=1.0,
    )
    db_session.add(seg)
    db_session.commit()

    res = client.patch(f"/api/v1/segments/{seg.id}", json={"title": "Nope"})
    assert res.status_code == 403
