from app.pipeline.classify import classify_dawarich_visit, classify_geofence_event


def test_classify_geofence_gym():
    activity, meta = classify_geofence_event(
        {"zone_name": "gym", "transition": "ENTER", "lat": 1.0, "lon": 2.0}
    )
    assert activity == "sport"
    assert meta["zone_name"] == "gym"


def test_classify_geofence_home_skipped():
    activity, meta = classify_geofence_event(
        {"zone_name": "home", "transition": "ENTER", "lat": 1.0, "lon": 2.0}
    )
    assert activity is None
    assert meta["exclude_from_windows"] is True


def test_classify_dawarich_restaurant_tag():
    activity, _ = classify_dawarich_visit(
        {
            "id": 1,
            "place": {"tags": {"amenity": "restaurant"}, "name": "Sushi"},
        }
    )
    assert activity == "eat"
