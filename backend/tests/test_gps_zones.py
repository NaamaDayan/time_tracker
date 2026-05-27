import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.gps_zone import GpsZone


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


class TestListZones:
    def test_empty_list(self, client):
        res = client.get("/api/v1/settings/zones/")
        assert res.status_code == 200
        assert res.json() == []

    def test_returns_enabled_zones_ordered(self, client, db_session):
        res1 = client.post(
            "/api/v1/settings/zones/",
            json={"name": "Gym", "category": "gym", "lat": 32.08, "lon": 34.78},
        )
        res2 = client.post(
            "/api/v1/settings/zones/",
            json={"name": "Beach", "category": "social", "lat": 32.09, "lon": 34.77},
        )
        assert res1.status_code == 201
        assert res2.status_code == 201

        res = client.get("/api/v1/settings/zones/")
        names = [z["name"] for z in res.json()]
        assert names == ["Beach", "Gym"]


class TestCreateZone:
    def test_create_with_defaults(self, client):
        res = client.post(
            "/api/v1/settings/zones/",
            json={
                "name": "My Gym",
                "category": "gym",
                "lat": 32.079,
                "lon": 34.781,
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "My Gym"
        assert data["category"] == "gym"
        assert data["activity_type_slug"] == "sport"
        assert data["radius_meters"] == 150
        assert data["enabled"] is True
        assert "id" in data
        assert "created_at" in data

    def test_create_with_explicit_activity_type(self, client):
        res = client.post(
            "/api/v1/settings/zones/",
            json={
                "name": "Office",
                "category": "work",
                "lat": 32.14,
                "lon": 34.80,
                "activity_type_slug": "communication",
            },
        )
        assert res.status_code == 201
        assert res.json()["activity_type_slug"] == "communication"

    def test_create_with_custom_radius(self, client):
        res = client.post(
            "/api/v1/settings/zones/",
            json={
                "name": "Home",
                "category": "home",
                "lat": 32.08,
                "lon": 34.78,
                "radius_meters": 75,
            },
        )
        assert res.status_code == 201
        assert res.json()["radius_meters"] == 75
        assert res.json()["activity_type_slug"] is None

    def test_duplicate_name_conflict(self, client):
        client.post(
            "/api/v1/settings/zones/",
            json={"name": "Office", "category": "work", "lat": 32.14, "lon": 34.80},
        )
        res = client.post(
            "/api/v1/settings/zones/",
            json={"name": "Office", "category": "work", "lat": 32.15, "lon": 34.81},
        )
        assert res.status_code == 409


class TestUpdateZone:
    def test_update_name_and_radius(self, client):
        create = client.post(
            "/api/v1/settings/zones/",
            json={"name": "Place", "category": "other", "lat": 32.08, "lon": 34.78},
        )
        zone_id = create.json()["id"]

        res = client.patch(
            f"/api/v1/settings/zones/{zone_id}",
            json={"name": "New Place", "radius_meters": 250},
        )
        assert res.status_code == 200
        assert res.json()["name"] == "New Place"
        assert res.json()["radius_meters"] == 250

    def test_update_category_recalculates_activity(self, client):
        create = client.post(
            "/api/v1/settings/zones/",
            json={"name": "Spot", "category": "gym", "lat": 32.08, "lon": 34.78},
        )
        zone_id = create.json()["id"]
        assert create.json()["activity_type_slug"] == "sport"

        res = client.patch(
            f"/api/v1/settings/zones/{zone_id}",
            json={"category": "work"},
        )
        assert res.status_code == 200
        assert res.json()["activity_type_slug"] == "work"

    def test_update_nonexistent_returns_404(self, client):
        res = client.patch(
            "/api/v1/settings/zones/00000000-0000-0000-0000-000000000000",
            json={"name": "Nope"},
        )
        assert res.status_code == 404


class TestDeleteZone:
    def test_delete_zone(self, client, db_session):
        create = client.post(
            "/api/v1/settings/zones/",
            json={"name": "Temp", "category": "other", "lat": 32.08, "lon": 34.78},
        )
        zone_id = create.json()["id"]

        res = client.delete(f"/api/v1/settings/zones/{zone_id}")
        assert res.status_code == 204

        listing = client.get("/api/v1/settings/zones/")
        assert listing.json() == []

    def test_delete_nonexistent_returns_404(self, client):
        res = client.delete(
            "/api/v1/settings/zones/00000000-0000-0000-0000-000000000000"
        )
        assert res.status_code == 404
