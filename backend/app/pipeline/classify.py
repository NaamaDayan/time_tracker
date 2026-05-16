from pathlib import Path
from typing import Any

import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


def load_clockify_rules() -> dict[str, Any]:
    path = RULES_DIR / "clockify.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def load_google_calendar_rules() -> dict[str, Any]:
    path = RULES_DIR / "google_calendar.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


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
        "calendar_id": event.get("organizer", {}).get("email") if isinstance(event.get("organizer"), dict) else None,
        "html_link": event.get("htmlLink"),
        "location": event.get("location"),
        "is_all_day": is_all_day,
    }
    return activity, metadata
