from pathlib import Path
from typing import Any

import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

_SUPPORTED_SOURCES = frozenset({"clockify", "google_calendar", "samsung_health"})


def load_clockify_rules() -> dict[str, Any]:
    path = RULES_DIR / "clockify.yaml"
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


def classify_raw_event(source: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Single entry point for all activity-type classification rules."""
    if source == "clockify":
        return classify_clockify_entry(payload)
    if source == "google_calendar":
        return classify_google_calendar_event(payload)
    if source == "samsung_health":
        return classify_samsung_health_record(payload)
    raise ValueError(f"Unknown source for classification: {source}")


def classify_clockify_entry(entry: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    rules = load_clockify_rules()
    activity = rules.get("default_activity", "work")
    project = entry.get("project") or {}
    auto = entry.get("_autoTracker") if isinstance(entry.get("_autoTracker"), dict) else {}
    metadata = {
        "project": project.get("name") if isinstance(project, dict) else None,
        "description": entry.get("description"),
        "tags": [t.get("name") for t in (entry.get("tags") or []) if isinstance(t, dict)],
        "app": auto.get("app"),
        "window": auto.get("window"),
        "url": auto.get("url"),
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


def classify_raw_event_safe(source: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Classify when source is known; return None for unsupported sources."""
    if source not in _SUPPORTED_SOURCES:
        return None
    return classify_raw_event(source, payload)
