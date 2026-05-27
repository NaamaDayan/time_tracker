import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.geofence.schemas import GeofenceEventIn
from app.connectors.sync_state import upsert_raw_event, write_sync_state
from app.models import ActivitySegment, SourceAccount
from app.pipeline.classify import apply_rule_config_filters, classify_geofence_event
from app.pipeline.windows.service import recompute_windows_for_segments

logger = logging.getLogger(__name__)

SOURCE = "geofence"


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_or_create_account(db: Session) -> SourceAccount:
    account = db.query(SourceAccount).filter(SourceAccount.source == SOURCE).first()
    if not account:
        account = SourceAccount(
            source=SOURCE,
            display_name="Geofence zones",
            config_json={},
            is_active=True,
        )
        db.add(account)
        db.flush()
    return account


def _open_geofence_segment(db: Session, zone_name: str) -> ActivitySegment | None:
    rows = (
        db.query(ActivitySegment)
        .filter(
            ActivitySegment.source == SOURCE,
            ActivitySegment.ended_at.is_(None),
        )
        .all()
    )
    for row in rows:
        meta = row.metadata_ or {}
        if meta.get("zone_name") == zone_name:
            return row
    return None


def _close_other_open_for_zone(db: Session, zone_name: str, ended_at: datetime) -> None:
    rows = (
        db.query(ActivitySegment)
        .filter(
            ActivitySegment.source == SOURCE,
            ActivitySegment.ended_at.is_(None),
        )
        .all()
    )
    for row in rows:
        meta = row.metadata_ or {}
        if meta.get("zone_name") == zone_name:
            row.ended_at = ended_at


def handle_geofence_event(db: Session, event: GeofenceEventIn) -> dict[str, Any]:
    """Upsert raw geofence event and open/close activity segments."""
    account = _get_or_create_account(db)
    ts = _ensure_utc(event.timestamp)
    external_id = f"{event.zone_name}_{event.transition}_{int(ts.timestamp())}"
    payload: dict[str, Any] = {
        "zone_name": event.zone_name,
        "transition": event.transition,
        "lat": event.lat,
        "lon": event.lon,
        "timestamp": ts.isoformat(),
    }

    raw_id = upsert_raw_event(
        db,
        source=SOURCE,
        external_id=external_id,
        started_at=ts,
        ended_at=ts,
        payload=payload,
    )

    activity_slug, metadata = classify_geofence_event(payload, db=db)
    if activity_slug is not None:
        from app.pipeline.rule_config import get_rule_config

        if not get_rule_config(activity_slug, db).enabled:
            activity_slug = None
        elif event.transition == "ENTER":
            filtered = apply_rule_config_filters(
                activity_slug,
                metadata,
                source=SOURCE,
                db=db,
                started_at=ts,
                ended_at=None,
            )
            if filtered is None:
                activity_slug = None
            else:
                activity_slug, metadata = filtered
    segment_id: int | None = None
    closed_segment_ids: list[int] = []

    if event.transition == "ENTER":
        if activity_slug:
            _close_other_open_for_zone(db, event.zone_name, ts)
            existing = _open_geofence_segment(db, event.zone_name)
            if existing is None:
                segment = ActivitySegment(
                    started_at=ts,
                    ended_at=None,
                    activity_type_slug=activity_slug,
                    source=SOURCE,
                    confidence=1.0,
                    metadata_={**metadata, "raw_event_id": raw_id},
                    raw_event_id=raw_id,
                )
                db.add(segment)
                db.flush()
                segment_id = segment.id
    elif event.transition == "EXIT":
        open_seg = _open_geofence_segment(db, event.zone_name)
        if open_seg is not None:
            filtered = apply_rule_config_filters(
                open_seg.activity_type_slug,
                open_seg.metadata_ or {},
                source=SOURCE,
                db=db,
                started_at=open_seg.started_at,
                ended_at=ts,
            )
            if filtered is None:
                db.delete(open_seg)
                db.flush()
                open_seg = None
            else:
                open_seg.ended_at = ts
        if open_seg is not None:
            meta = dict(open_seg.metadata_ or {})
            meta["exit_raw_event_id"] = raw_id
            open_seg.metadata_ = meta
            segment_id = open_seg.id
            closed_segment_ids.append(open_seg.id)

    db.commit()

    if closed_segment_ids:
        recompute_windows_for_segments(db, closed_segment_ids)

    write_sync_state(
        db,
        account,
        last_event_at=ts.isoformat(),
        last_zone=event.zone_name,
        last_transition=event.transition,
    )

    logger.info(
        "Geofence %s %s zone=%s raw_id=%s segment_id=%s",
        event.transition,
        ts.isoformat(),
        event.zone_name,
        raw_id,
        segment_id,
    )

    return {
        "raw_id": raw_id,
        "segment_id": segment_id,
        "external_id": external_id,
        "transition": event.transition,
        "zone_name": event.zone_name,
    }
