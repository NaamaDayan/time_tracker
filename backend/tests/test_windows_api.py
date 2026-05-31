from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import ActivitySegment, ActivityWindow
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
            source_manual=True,
            confidence=1.0,
        )
    )
    db_session.add(
        ActivitySegment(
            started_at=base + timedelta(minutes=21),
            ended_at=base + timedelta(hours=1),
            activity_type_slug="work",
            source="manual",
            source_manual=True,
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
    w0 = data["windows"][0]
    assert "confidence" in w0
    assert "confirmed_by_user" in w0
    assert "dismissed_by_user" in w0
    assert "segment_count" in w0


def test_patch_confirm_and_dismiss(client, db_session):
    base = datetime(2026, 5, 17, 10, 0, tzinfo=UTC)
    db_session.add(
        ActivitySegment(
            started_at=base,
            ended_at=base + timedelta(minutes=30),
            activity_type_slug="work",
            source="activitywatch_desktop",
            source_manual=False,
            confidence=0.55,
        )
    )
    db_session.commit()
    backfill_all_windows(db_session)
    win_id = db_session.query(ActivityWindow).first().id

    r = client.patch(f"/api/v1/windows/{win_id}", json={"confirmed_by_user": True})
    assert r.status_code == 200
    assert r.json()["confirmed_by_user"] is True

    r = client.patch(f"/api/v1/windows/{win_id}", json={"dismissed_by_user": True})
    assert r.status_code == 200
    assert r.json()["dismissed_by_user"] is True

    from_ = base.isoformat()
    to = (base + timedelta(days=1)).isoformat()
    r = client.get("/api/v1/windows", params={"from": from_, "to": to})
    assert r.json()["windows"] == []

    r = client.get(
        "/api/v1/windows",
        params={"from": from_, "to": to, "include_dismissed": "true"},
    )
    assert len(r.json()["windows"]) == 1


def test_patch_type_correction(client, db_session):
    base = datetime(2026, 5, 18, 10, 0, tzinfo=UTC)
    db_session.add(
        ActivitySegment(
            started_at=base,
            ended_at=base + timedelta(minutes=40),
            activity_type_slug="work",
            source="activitywatch_desktop",
            source_manual=False,
            confidence=0.6,
        )
    )
    db_session.commit()
    backfill_all_windows(db_session)
    win_id = db_session.query(ActivityWindow).first().id

    r = client.patch(
        f"/api/v1/windows/{win_id}",
        json={"activity_type_slug": "family"},
    )
    assert r.status_code == 200
    new = r.json()
    assert new["activity_type"] == "family"
    assert new["confidence"] == 1.0
    assert new["correction_of_window_id"] == win_id

    dismissed = db_session.get(ActivityWindow, win_id)
    assert dismissed.dismissed_by_user is True


def test_post_manual_window(client, db_session):
    base = datetime(2026, 5, 19, 13, 0, tzinfo=UTC)
    r = client.post(
        "/api/v1/windows/manual",
        json={
            "activity_type_slug": "fun",
            "started_at": base.isoformat(),
            "ended_at": (base + timedelta(minutes=50)).isoformat(),
            "note": "lunch",
        },
    )
    assert r.status_code == 200
    assert r.json()["activity_type"] == "fun"
    assert r.json()["confidence"] == 1.0


def test_delete_manual_correction_restores_original(client, db_session):
    base = datetime(2026, 5, 20, 10, 0, tzinfo=UTC)
    db_session.add(
        ActivitySegment(
            started_at=base,
            ended_at=base + timedelta(minutes=40),
            activity_type_slug="work",
            source="activitywatch_desktop",
            source_manual=False,
            confidence=0.6,
        )
    )
    db_session.commit()
    backfill_all_windows(db_session)
    win_id = db_session.query(ActivityWindow).first().id

    r = client.patch(
        f"/api/v1/windows/{win_id}",
        json={"activity_type_slug": "family"},
    )
    new_id = r.json()["id"]

    r = client.delete(f"/api/v1/windows/manual/{new_id}")
    assert r.status_code == 204

    from_ = base.isoformat()
    to = (base + timedelta(days=1)).isoformat()
    r = client.get("/api/v1/windows", params={"from": from_, "to": to})
    types = {w["activity_type"] for w in r.json()["windows"]}
    assert "work" in types


def test_type_correction_merges_existing_same_type_window(client, db_session):
    base = datetime(2026, 5, 22, 10, 0, tzinfo=UTC)
    db_session.add(
        ActivitySegment(
            started_at=base,
            ended_at=base + timedelta(hours=1),
            activity_type_slug="family",
            source="manual",
            source_manual=True,
            confidence=1.0,
        )
    )
    db_session.add(
        ActivitySegment(
            started_at=base + timedelta(minutes=50),
            ended_at=base + timedelta(hours=1, minutes=30),
            activity_type_slug="work",
            source="activitywatch_desktop",
            source_manual=False,
            confidence=0.6,
        )
    )
    db_session.commit()
    backfill_all_windows(db_session)
    work_win = (
        db_session.query(ActivityWindow)
        .filter(ActivityWindow.activity_type_slug == "work")
        .first()
    )

    r = client.patch(
        f"/api/v1/windows/{work_win.id}",
        json={"activity_type_slug": "family"},
    )
    assert r.status_code == 200
    family_windows = (
        db_session.query(ActivityWindow)
        .filter(
            ActivityWindow.activity_type_slug == "family",
            ActivityWindow.dismissed_by_user.is_(False),
        )
        .all()
    )
    assert len(family_windows) == 1
    assert family_windows[0].segment_count >= 2


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
