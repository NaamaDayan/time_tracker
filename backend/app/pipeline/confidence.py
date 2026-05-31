"""Deterministic confidence scoring for classified segments and derived windows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models import ActivitySegment, RawEvent

GPS_SOURCES = frozenset({"geofence", "dawarich"})
WATCH_HEALTH_SOURCES = frozenset({"samsung_health"})
INFERRED_SOURCES = frozenset({"activitywatch_desktop", "activitywatch"})


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _duration_minutes(started_at: datetime | None, ended_at: datetime | None) -> float | None:
    if started_at is None or ended_at is None:
        return None
    return (_ensure_utc(ended_at) - _ensure_utc(started_at)).total_seconds() / 60.0


def _has_corroboration(
    source: str,
    metadata: dict[str, Any],
    payload: dict[str, Any] | None,
) -> bool:
    if metadata.get("corroborated") is True:
        return True
    if metadata.get("watch_confirmed") is True:
        return True
    sources = metadata.get("sources")
    if isinstance(sources, list) and len(sources) > 1:
        return True
    if payload:
        if payload.get("watch_active") or payload.get("watch_confirmed"):
            return True
        if payload.get("corroborated"):
            return True
    return source in GPS_SOURCES and (
        metadata.get("watch_active") is True or metadata.get("hevy_open") is True
    )


def _boost_signal_active(
    boost_signals: dict[str, Any],
    metadata: dict[str, Any],
    payload: dict[str, Any] | None,
) -> bool:
    for key, enabled in boost_signals.items():
        if not enabled:
            continue
        if metadata.get(key) is True:
            return True
        if payload and payload.get(key) is True:
            return True
    return False


def score_segment_confidence(
    raw_event: RawEvent | None,
    *,
    activity_type_slug: str,
    source: str,
    metadata: dict[str, Any] | None,
    db: Session,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    payload: dict[str, Any] | None = None,
) -> float:
    """
    Called during classification. Returns 0.1–1.0.
    Stored on ActivitySegment.confidence at creation time.
    """
    from app.pipeline.rule_config import get_rule_config

    meta = dict(metadata or {})
    if raw_event is not None:
        payload = payload if payload is not None else raw_event.payload
        source = raw_event.source
        started_at = started_at or raw_event.started_at
        ended_at = ended_at or raw_event.ended_at
    else:
        payload = payload or {}

    cfg = get_rule_config(activity_type_slug, db)
    min_dur = cfg.min_duration_minutes
    duration = _duration_minutes(started_at, ended_at)

    base = 0.7
    adjustments = 0.0

    if source in GPS_SOURCES and duration is not None and duration >= min_dur:
        adjustments += 0.2

    if _has_corroboration(source, meta, payload):
        adjustments += 0.1

    boost = cfg.boost_signals or {}
    if _boost_signal_active(boost, meta, payload):
        adjustments += 0.1

    has_gps = source in GPS_SOURCES
    has_watch = source in WATCH_HEALTH_SOURCES or meta.get("watch_confirmed") or meta.get(
        "watch_active"
    )
    if not has_gps and not has_watch and source in INFERRED_SOURCES.union(
        {"google_calendar"}
    ):
        adjustments -= 0.2

    if duration is not None and min_dur > 0:
        threshold_upper = min_dur * 1.2
        if min_dur <= duration < threshold_upper:
            adjustments -= 0.1

    if source in INFERRED_SOURCES and not _has_corroboration(source, meta, payload):
        adjustments -= 0.1

    if duration is not None and duration < 10 and source in INFERRED_SOURCES:
        adjustments -= 0.1

    return round(max(0.1, min(1.0, base + adjustments)), 2)


def derive_window_confidence(window_id: int, db: Session) -> float:
    """Return min confidence across constituent segments for a persisted window."""
    from app.models import ActivitySegment, ActivityWindowSegment

    segment_confidences = (
        db.query(ActivitySegment.confidence)
        .join(
            ActivityWindowSegment,
            ActivityWindowSegment.segment_id == ActivitySegment.id,
        )
        .filter(ActivityWindowSegment.window_id == window_id)
        .all()
    )
    if not segment_confidences:
        return 1.0
    return round(min(c[0] for c in segment_confidences), 2)


def segment_user_confirmed(metadata: dict[str, Any] | None) -> bool:
    return bool((metadata or {}).get("user_confirmed"))


def segment_excluded_from_windows(metadata: dict[str, Any] | None) -> bool:
    return (metadata or {}).get("exclude_from_windows") is True
