"""Helpers for window-level user corrections."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import ActivitySegment, ActivityType, ActivityWindow, ActivityWindowSegment
from app.pipeline.rule_config import get_rule_config
from app.pipeline.windows.service import recompute_windows_after_segment_change

MANUAL_SOURCE = "manual"


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _segment_ids_for_window(db: Session, window_id: int) -> list[int]:
    links = (
        db.query(ActivityWindowSegment.segment_id)
        .filter(ActivityWindowSegment.window_id == window_id)
        .all()
    )
    return [row[0] for row in links]


def _set_segments_exclude(db: Session, segment_ids: list[int], *, exclude: bool) -> None:
    for seg_id in segment_ids:
        seg = db.get(ActivitySegment, seg_id)
        if seg is None:
            continue
        meta = dict(seg.metadata_ or {})
        if exclude:
            meta["exclude_from_windows"] = True
        else:
            meta.pop("exclude_from_windows", None)
        seg.metadata_ = meta or None


def _set_segments_user_confirmed(db: Session, segment_ids: list[int], *, confirmed: bool) -> None:
    for seg_id in segment_ids:
        seg = db.get(ActivitySegment, seg_id)
        if seg is None:
            continue
        meta = dict(seg.metadata_ or {})
        if confirmed:
            meta["user_confirmed"] = True
        else:
            meta.pop("user_confirmed", None)
        seg.metadata_ = meta or None


def confirm_window(db: Session, window: ActivityWindow) -> ActivityWindow:
    window.confirmed_by_user = True
    _set_segments_user_confirmed(db, _segment_ids_for_window(db, window.id), confirmed=True)
    return window


def dismiss_window(db: Session, window: ActivityWindow) -> ActivityWindow:
    window.dismissed_by_user = True
    _set_segments_exclude(db, _segment_ids_for_window(db, window.id), exclude=True)
    return window


def create_manual_segment(
    db: Session,
    *,
    activity_type_slug: str,
    started_at: datetime,
    ended_at: datetime,
    note: str | None = None,
) -> ActivitySegment:
    metadata: dict = {}
    if note:
        metadata["note"] = note
    seg = ActivitySegment(
        started_at=_ensure_utc(started_at),
        ended_at=_ensure_utc(ended_at),
        activity_type_slug=activity_type_slug,
        source=MANUAL_SOURCE,
        source_manual=True,
        confidence=1.0,
        metadata_=metadata or None,
        raw_event_id=None,
    )
    db.add(seg)
    db.flush()
    return seg


def find_covering_window(
    db: Session,
    *,
    activity_type_slug: str,
    started_at: datetime,
    ended_at: datetime,
) -> ActivityWindow | None:
    started_at = _ensure_utc(started_at)
    ended_at = _ensure_utc(ended_at)
    return (
        db.query(ActivityWindow)
        .filter(
            ActivityWindow.activity_type_slug == activity_type_slug,
            ActivityWindow.dismissed_by_user.is_(False),
            ActivityWindow.started_at <= ended_at,
            ActivityWindow.ended_at >= started_at,
        )
        .order_by(ActivityWindow.computed_at.desc())
        .first()
    )


def recompute_for_manual_segment(
    db: Session,
    seg: ActivitySegment,
    *,
    extra_types: set[str] | None = None,
) -> None:
    types = {seg.activity_type_slug} | (extra_types or set())
    recompute_windows_after_segment_change(
        db,
        segment_ids=[seg.id],
        extra_types=types,
        bounds_from_segments=[seg],
    )


def validate_manual_duration(db: Session, slug: str, started_at: datetime, ended_at: datetime) -> None:
    from fastapi import HTTPException

    started_at = _ensure_utc(started_at)
    ended_at = _ensure_utc(ended_at)
    if ended_at <= started_at:
        raise HTTPException(status_code=400, detail="ended_at must be after started_at")
    duration_min = (ended_at - started_at).total_seconds() / 60.0
    min_required = get_rule_config(slug, db).min_duration_minutes
    if duration_min < min_required:
        raise HTTPException(
            status_code=400,
            detail=f"Duration must be at least {min_required} minutes for this activity type",
        )


def validate_activity_type(db: Session, slug: str) -> ActivityType:
    from fastapi import HTTPException

    atype = db.query(ActivityType).filter(ActivityType.slug == slug).first()
    if not atype:
        raise HTTPException(status_code=400, detail=f"Unknown activity type: {slug}")
    cfg = get_rule_config(slug, db)
    if not cfg.enabled:
        raise HTTPException(status_code=400, detail=f"Activity type '{slug}' is disabled")
    return atype


def undelete_original_correction(db: Session, original_window_id: int) -> None:
    original = db.get(ActivityWindow, original_window_id)
    if original is None:
        return
    original.dismissed_by_user = False
    _set_segments_exclude(db, _segment_ids_for_window(db, original_window_id), exclude=False)
