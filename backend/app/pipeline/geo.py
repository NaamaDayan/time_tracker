import math

from sqlalchemy.orm import Session

from app.models.gps_zone import GpsZone

EARTH_RADIUS_METERS = 6_371_000


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in meters between two points."""
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)

    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_METERS * c


def get_zone_for_point(lat: float, lon: float, db: Session) -> GpsZone | None:
    """Find the nearest enabled zone whose radius contains the given point.

    If multiple zones contain the point, the one with the shortest distance
    from the point to the zone center wins.
    """
    zones = db.query(GpsZone).filter(GpsZone.enabled.is_(True)).all()

    best: GpsZone | None = None
    best_distance = float("inf")

    for zone in zones:
        distance = haversine_meters(lat, lon, zone.lat, zone.lon)
        if distance <= zone.radius_meters and distance < best_distance:
            best = zone
            best_distance = distance

    return best
