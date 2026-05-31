import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pipeline.activity_priority import invalidate_activity_priority_cache
from app.seed_activity_type_priority import DEFAULT_PRIORITY, seed_activity_type_priority


@pytest.fixture
def api_client(db_session):
    from app.database import get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _auth_headers():
    return {"X-API-Key": "test-key"}


def test_get_priority_default_order(api_client, db_session, monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    response = api_client.get(
        "/api/v1/settings/activity-priority/",
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 14
    assert [item["slug"] for item in data] == DEFAULT_PRIORITY
    assert [item["rank"] for item in data] == list(range(1, 15))


def test_put_reorder_persists(api_client, monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    get_resp = api_client.get(
        "/api/v1/settings/activity-priority/",
        headers=_auth_headers(),
    )
    items = get_resp.json()
    swapped = items.copy()
    swapped[0], swapped[1] = swapped[1], swapped[0]
    body = [{"slug": i["slug"], "rank": idx + 1} for idx, i in enumerate(swapped)]

    put_resp = api_client.put(
        "/api/v1/settings/activity-priority/",
        json=body,
        headers=_auth_headers(),
    )
    assert put_resp.status_code == 200
    assert put_resp.json()[0]["slug"] == swapped[0]["slug"]

    get_again = api_client.get(
        "/api/v1/settings/activity-priority/",
        headers=_auth_headers(),
    )
    assert get_again.json()[0]["slug"] == swapped[0]["slug"]


def test_put_duplicate_rank_400(api_client, monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    get_resp = api_client.get(
        "/api/v1/settings/activity-priority/",
        headers=_auth_headers(),
    )
    items = get_resp.json()
    body = [{"slug": i["slug"], "rank": 1} for i in items]

    response = api_client.put(
        "/api/v1/settings/activity-priority/",
        json=body,
        headers=_auth_headers(),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Duplicate ranks not allowed"


def test_put_missing_slug_400(api_client, monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    get_resp = api_client.get(
        "/api/v1/settings/activity-priority/",
        headers=_auth_headers(),
    )
    items = get_resp.json()[:-1]
    body = [{"slug": i["slug"], "rank": idx + 1} for idx, i in enumerate(items)]

    response = api_client.put(
        "/api/v1/settings/activity-priority/",
        json=body,
        headers=_auth_headers(),
    )
    assert response.status_code == 400
    assert "Missing activity types: transport" in response.json()["detail"]


def test_seed_idempotent(db_session):
    from app.models import ActivityTypePriority

    invalidate_activity_priority_cache()
    first = seed_activity_type_priority(db_session)
    assert first == 0
    assert db_session.query(ActivityTypePriority).count() == 14
