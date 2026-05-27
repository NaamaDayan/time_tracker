import uuid

import pytest

from app.models.gps_zone import GpsZone
from app.pipeline.geo import get_zone_for_point, haversine_meters


class TestHaversineMeters:
    def test_same_point_is_zero(self):
        assert haversine_meters(32.08, 34.78, 32.08, 34.78) == 0.0

    def test_tel_aviv_to_jerusalem(self):
        # ~60 km between Tel Aviv and Jerusalem
        d = haversine_meters(32.0853, 34.7818, 31.7683, 35.2137)
        assert 52_000 < d < 62_000

    def test_london_to_paris(self):
        # ~340 km
        d = haversine_meters(51.5074, -0.1278, 48.8566, 2.3522)
        assert 330_000 < d < 350_000

    def test_new_york_to_los_angeles(self):
        # ~3940 km
        d = haversine_meters(40.7128, -74.0060, 34.0522, -118.2437)
        assert 3_900_000 < d < 4_000_000

    def test_symmetric(self):
        d1 = haversine_meters(32.08, 34.78, 31.77, 35.21)
        d2 = haversine_meters(31.77, 35.21, 32.08, 34.78)
        assert abs(d1 - d2) < 0.01


class TestGetZoneForPoint:
    def _make_zone(self, name, lat, lon, radius, activity_slug=None):
        return GpsZone(
            id=uuid.uuid4(),
            name=name,
            category="other",
            activity_type_slug=activity_slug,
            lat=lat,
            lon=lon,
            radius_meters=radius,
            enabled=True,
        )

    def test_point_inside_single_zone(self, db_session):
        zone = self._make_zone("office", 32.0841, 34.7865, 200, "work")
        db_session.add(zone)
        db_session.commit()

        result = get_zone_for_point(32.0842, 34.7866, db_session)
        assert result is not None
        assert result.name == "office"

    def test_point_outside_all_zones(self, db_session):
        zone = self._make_zone("office", 32.0841, 34.7865, 50, "work")
        db_session.add(zone)
        db_session.commit()

        # ~5 km away
        result = get_zone_for_point(32.13, 34.80, db_session)
        assert result is None

    def test_overlapping_zones_nearest_wins(self, db_session):
        # Two zones that overlap: big zone (500m radius) and small zone (100m) closer
        big_zone = self._make_zone("neighborhood", 32.0841, 34.7865, 500, "fun")
        small_zone = self._make_zone("office", 32.0845, 34.7868, 100, "work")
        db_session.add_all([big_zone, small_zone])
        db_session.commit()

        # Point very close to the small zone center
        result = get_zone_for_point(32.0846, 34.7869, db_session)
        assert result is not None
        assert result.name == "office"

    def test_disabled_zone_excluded(self, db_session):
        zone = GpsZone(
            id=uuid.uuid4(),
            name="disabled_place",
            category="other",
            activity_type_slug="work",
            lat=32.0841,
            lon=34.7865,
            radius_meters=200,
            enabled=False,
        )
        db_session.add(zone)
        db_session.commit()

        result = get_zone_for_point(32.0842, 34.7866, db_session)
        assert result is None
