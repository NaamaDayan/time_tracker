from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import yaml

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

_SUPPORTED_SOURCES = frozenset(
    {
        "activitywatch_desktop",
        "google_calendar",
        "samsung_health",
        "activitywatch",
        "geofence",
        "dawarich",
    }
)


def load_activitywatch_desktop_rules() -> dict[str, Any]:
    path = RULES_DIR / "activitywatch_desktop.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def load_google_calendar_rules() -> dict[str, Any]:
    path = RULES_DIR / "google_calendar.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def load_samsung_health_rules() -> dict[str, Any]:
    path = RULES_DIR / "samsung_health.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def load_activitywatch_rules() -> dict[str, Any]:
    path = RULES_DIR / "activitywatch.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def load_location_zones_rules() -> dict[str, Any]:
    path = RULES_DIR / "location_zones.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def load_dawarich_rules() -> dict[str, Any]:
    path = RULES_DIR / "dawarich.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def _zone_rules_entry(rules: dict[str, Any], zone_name: str) -> dict[str, Any]:
    zones: dict[str, Any] = rules.get("zones") or {}
    entry = zones.get(zone_name)
    if isinstance(entry, dict):
        return entry
    return {"activity": rules.get("default_activity")}


def _activitywatch_match_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("app", "package", "title", "record_type"):
        val = payload.get(key)
        if val:
            parts.append(str(val))
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("app", "package", "title", "name"):
            val = data.get(key)
            if val:
                parts.append(str(val))
    return " ".join(parts).lower()


def classify_activitywatch_event(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    rules = load_activitywatch_rules()
    haystack = _activitywatch_match_text(payload)
    activity = rules.get("default_activity", "phone_usage")

    for rule in rules.get("app_rules") or []:
        if not isinstance(rule, dict):
            continue
        slug = rule.get("activity")
        terms = rule.get("match") or []
        if not slug or not isinstance(terms, list):
            continue
        if any(str(term).lower() in haystack for term in terms):
            activity = slug
            break

    app = payload.get("app")
    package = payload.get("package")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if not app and isinstance(data, dict):
        app = data.get("app") or data.get("name")
    if not package and isinstance(data, dict):
        package = data.get("package")

    metadata: dict[str, Any] = {
        "record_type": payload.get("record_type", "app_session"),
        "app": app,
        "package": package,
        "bucket_id": payload.get("bucket_id"),
        "aw_event_id": payload.get("aw_event_id"),
    }
    if payload.get("title"):
        metadata["title"] = payload["title"]

    return activity, metadata


def classify_geofence_event(
    payload: dict[str, Any], db: "Session | None" = None
) -> tuple[str | None, dict[str, Any]]:
    from sqlalchemy.orm import Session  # noqa: F811

    zone_name = str(payload.get("zone_name") or "")
    lat = payload.get("lat")
    lon = payload.get("lon")

    # Try DB-backed zone lookup first (by name or by coordinates)
    if db is not None:
        from app.models.gps_zone import GpsZone
        from app.pipeline.geo import get_zone_for_point

        db_zone = db.query(GpsZone).filter(
            GpsZone.name == zone_name, GpsZone.enabled.is_(True)
        ).first()

        if db_zone is None and lat is not None and lon is not None:
            db_zone = get_zone_for_point(float(lat), float(lon), db)

        if db_zone is not None:
            activity = db_zone.activity_type_slug
            exclude = activity is None
            metadata: dict[str, Any] = {
                "zone_name": db_zone.name,
                "transition": payload.get("transition"),
                "lat": lat,
                "lon": lon,
                "exclude_from_windows": bool(exclude),
                "zone_id": str(db_zone.id),
                "zone_category": db_zone.category,
            }
            return activity, metadata

    # Fallback to YAML rules
    rules = load_location_zones_rules()
    entry = _zone_rules_entry(rules, zone_name)
    activity = entry.get("activity")
    if activity is not None:
        activity = str(activity)
    exclude = entry.get("exclude_from_windows", activity is None)
    metadata = {
        "zone_name": zone_name,
        "transition": payload.get("transition"),
        "lat": lat,
        "lon": lon,
        "exclude_from_windows": bool(exclude),
    }
    return activity, metadata


def _dawarich_place_tags(payload: dict[str, Any]) -> dict[str, str]:
    place = payload.get("place")
    if not isinstance(place, dict):
        return {}
    tags = place.get("tags")
    if isinstance(tags, dict):
        return {str(k): str(v) for k, v in tags.items()}
    return {}


def _dawarich_place_name(payload: dict[str, Any]) -> str:
    for key in ("name",):
        if payload.get(key):
            return str(payload[key]).lower()
    place = payload.get("place")
    if isinstance(place, dict) and place.get("name"):
        return str(place["name"]).lower()
    return ""


def classify_dawarich_visit(payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    rules = load_dawarich_rules()
    activity: str | None = rules.get("default_activity")
    if activity is not None:
        activity = str(activity)
    exclude_from_windows = False

    tags = _dawarich_place_tags(payload)
    for rule in rules.get("osm_tag_rules") or []:
        if not isinstance(rule, dict):
            continue
        match = rule.get("match")
        if not isinstance(match, dict):
            continue
        if all(tags.get(str(k)) == str(v) for k, v in match.items()):
            activity = rule.get("activity")
            if activity is not None:
                activity = str(activity)
            exclude_from_windows = rule.get("exclude_from_windows", activity is None)
            break

    if activity is None:
        haystack = _dawarich_place_name(payload)
        for rule in rules.get("name_keyword_rules") or []:
            if not isinstance(rule, dict):
                continue
            terms = rule.get("match") or []
            if not isinstance(terms, list):
                continue
            if any(str(term).lower() in haystack for term in terms):
                activity = rule.get("activity")
                if activity is not None:
                    activity = str(activity)
                exclude_from_windows = rule.get("exclude_from_windows", activity is None)
                break

    place = payload.get("place") if isinstance(payload.get("place"), dict) else {}
    metadata: dict[str, Any] = {
        "place_name": place.get("name") or payload.get("name"),
        "dawarich_visit_id": payload.get("id"),
        "lat": place.get("latitude"),
        "lon": place.get("longitude"),
        "exclude_from_windows": bool(exclude_from_windows or activity is None),
    }
    return activity, metadata


def classify_raw_event(
    source: str,
    payload: dict[str, Any],
    *,
    db: "Session | None" = None,
) -> tuple[str | None, dict[str, Any]]:
    """Single entry point for all activity-type classification rules."""
    if source == "activitywatch_desktop":
        return classify_activitywatch_desktop_event(payload)
    if source == "google_calendar":
        return classify_google_calendar_event(payload)
    if source == "samsung_health":
        return classify_samsung_health_record(payload)
    if source == "activitywatch":
        return classify_activitywatch_event(payload)
    if source == "geofence":
        return classify_geofence_event(payload, db=db)
    if source == "dawarich":
        return classify_dawarich_visit(payload)
    raise ValueError(f"Unknown source for classification: {source}")


def _js_weekday(dt: datetime) -> int:
    """Sunday=0 .. Saturday=6 (matches frontend day pills)."""
    return (dt.weekday() + 1) % 7


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _local_hour(dt: datetime, tz_name: str) -> float:
    local = _ensure_utc(dt).astimezone(ZoneInfo(tz_name))
    return local.hour + local.minute / 60.0 + local.second / 3600.0


def _passes_work_schedule(
    started_at: datetime,
    custom_params: dict[str, Any],
    tz_name: str,
) -> bool:
    work_days = custom_params.get("work_days")
    if isinstance(work_days, list) and work_days:
        if _js_weekday(_ensure_utc(started_at)) not in work_days:
            return False
    start_h = custom_params.get("work_hours_start")
    end_h = custom_params.get("work_hours_end")
    if start_h is not None and end_h is not None:
        hour = _local_hour(started_at, tz_name)
        start_f = float(start_h)
        end_f = float(end_h)
        if start_f <= end_f:
            if not (start_f <= hour < end_f):
                return False
        else:
            if not (hour >= start_f or hour < end_f):
                return False
    return True


def _segment_duration_minutes(started_at: datetime, ended_at: datetime) -> float:
    return (_ensure_utc(ended_at) - _ensure_utc(started_at)).total_seconds() / 60.0


def apply_rule_config_filters(
    activity: str,
    metadata: dict[str, Any],
    *,
    source: str,
    db: "Session",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> tuple[str, dict[str, Any]] | None:
    from app.config import get_settings
    from app.pipeline.rule_config import get_rule_config

    cfg = get_rule_config(activity, db)
    if not cfg.enabled:
        return None

    if (
        started_at is not None
        and ended_at is not None
        and _ensure_utc(ended_at) > _ensure_utc(started_at)
    ):
        duration_min = _segment_duration_minutes(started_at, ended_at)
        if duration_min < cfg.min_duration_minutes:
            return None

    if activity == "work" and source == "activitywatch_desktop" and started_at is not None:
        params = cfg.custom_params or {}
        if not _passes_work_schedule(started_at, params, get_settings().user_timezone):
            return None

    return activity, metadata


def classify_activitywatch_desktop_event(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    rules = load_activitywatch_desktop_rules()
    app = payload.get("app") or ""
    title = payload.get("title") or ""
    haystack = f"{app} {title}".lower()
    activity = rules.get("default_activity", "work")

    for rule in rules.get("app_rules") or []:
        if not isinstance(rule, dict):
            continue
        slug = rule.get("activity")
        terms = rule.get("match") or []
        if not slug or not isinstance(terms, list):
            continue
        if any(str(term).lower() in haystack for term in terms):
            activity = slug
            break

    metadata: dict[str, Any] = {
        "app": app or None,
        "title": title or None,
        "bucket_id": payload.get("bucket_id"),
        "aw_event_id": payload.get("aw_event_id"),
    }
    return activity, metadata


def classify_google_calendar_event(event: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    rules = load_google_calendar_rules()
    title = (event.get("summary") or "").lower()
    activity = rules.get("default_activity", "communication")
    keywords: dict[str, list[str]] = rules.get("title_keywords") or {}
    for slug, terms in keywords.items():
        if not isinstance(terms, list):
            continue
        if any(str(term).lower() in title for term in terms):
            activity = slug
            break

    start = event.get("start") or {}
    is_all_day = "date" in start and "dateTime" not in start
    metadata = {
        "summary": event.get("summary"),
        "calendar_id": event.get("organizer", {}).get("email")
        if isinstance(event.get("organizer"), dict)
        else None,
        "html_link": event.get("htmlLink"),
        "location": event.get("location"),
        "is_all_day": is_all_day,
    }
    return activity, metadata


def classify_samsung_health_record(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    rules = load_samsung_health_rules()
    record_types: dict[str, dict[str, Any]] = rules.get("record_types") or {}
    record_type = payload.get("record_type") or ""
    type_rules = record_types.get(record_type, {})

    activity = type_rules.get("activity", "sport")
    health_category = type_rules.get("health_category", record_type)
    calendar_visible = type_rules.get("calendar_visible", True)
    exclude_from_windows = type_rules.get("exclude_from_windows", False)

    metadata: dict[str, Any] = {
        "record_type": record_type,
        "health_category": health_category,
        "calendar_visible": calendar_visible,
        "exclude_from_windows": exclude_from_windows,
    }

    if record_type == "sleep_session":
        metadata["woke_at"] = payload.get("ended_at") or payload.get("woke_at")
        if payload.get("duration_min") is not None:
            metadata["duration_min"] = payload["duration_min"]
        if payload.get("sessions"):
            metadata["sessions"] = payload["sessions"]
    elif record_type == "exercise_session":
        if payload.get("exercise_type"):
            metadata["exercise_type"] = payload["exercise_type"]
        if payload.get("calories") is not None:
            metadata["calories"] = payload["calories"]
        if payload.get("duration_sec") is not None:
            metadata["duration_sec"] = payload["duration_sec"]
    elif record_type == "daily_steps":
        if payload.get("step_count") is not None:
            metadata["step_count"] = payload["step_count"]
        if payload.get("local_date"):
            metadata["local_date"] = payload["local_date"]

    return activity, metadata


def classify_raw_event_safe(
    source: str,
    payload: dict[str, Any],
    *,
    db: "Session | None" = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Classify when source is known; return None for unsupported sources or skip-segment rules."""
    if source not in _SUPPORTED_SOURCES:
        return None
    activity, metadata = classify_raw_event(source, payload, db=db)
    if activity is None:
        return None
    if db is not None:
        filtered = apply_rule_config_filters(
            activity,
            metadata,
            source=source,
            db=db,
            started_at=started_at,
            ended_at=ended_at,
        )
        return filtered
    return activity, metadata
