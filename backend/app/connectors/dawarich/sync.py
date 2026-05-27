import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors.dawarich.client import DawarichClient
from app.connectors.dawarich.dedup import geofence_covers_visit
from app.connectors.sync_state import upsert_raw_event, write_sync_state
from app.models import ActivitySegment, RawEvent, SourceAccount
from app.pipeline.classify import classify_dawarich_visit
from app.pipeline.normalize import rebuild_segments_for_raw_events
from app.pipeline.windows.service import recompute_windows_for_segments

logger = logging.getLogger(__name__)

SOURCE = "dawarich"


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_visit_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    return _ensure_utc(dt)


def visit_times_from_payload(visit: dict[str, Any]) -> tuple[datetime, datetime]:
    started = _parse_visit_time(visit.get("started_at"))
    ended = _parse_visit_time(visit.get("ended_at"))
    if not started:
        raise ValueError(f"Dawarich visit {visit.get('id')} missing started_at")
    if not ended or ended <= started:
        duration_min = visit.get("duration")
        if isinstance(duration_min, (int, float)) and duration_min > 0:
            ended = started + timedelta(minutes=float(duration_min))
        else:
            ended = started + timedelta(minutes=30)
    return started, ended


def _get_or_create_account(db: Session) -> SourceAccount:
    account = db.query(SourceAccount).filter(SourceAccount.source == SOURCE).first()
    if not account:
        account = SourceAccount(
            source=SOURCE,
            display_name="Dawarich visits",
            config_json={},
            is_active=True,
        )
        db.add(account)
        db.flush()
    elif not account.is_active:
        account.is_active = True
    return account


def _should_skip_for_geofence(
    db: Session, visit: dict[str, Any], started: datetime, ended: datetime
) -> bool:
    place = visit.get("place") if isinstance(visit.get("place"), dict) else {}
    place_name = place.get("name") or visit.get("name")
    covering = geofence_covers_visit(
        db,
        visit_start=started,
        visit_end=ended,
        place_name=str(place_name) if place_name else None,
    )
    return covering is not None


def sync_dawarich(
    db: Session,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.dawarich_sync_enabled:
        return {"skipped": True, "reason": "dawarich_sync_disabled"}

    tz = ZoneInfo(settings.user_timezone)
    now = datetime.now(timezone.utc)

    if until is None:
        until = datetime.combine(date.today(), time.min, tzinfo=tz).astimezone(timezone.utc)
    if since is None:
        since = until - timedelta(days=1)

    since = _ensure_utc(since)
    until = _ensure_utc(until)

    account = _get_or_create_account(db)
    client = DawarichClient()
    visits = client.fetch_visits(since, until)

    touched_ids: list[int] = []
    skipped_geofence = 0
    skipped_unclassified = 0

    for visit in visits:
        if not isinstance(visit, dict):
            continue
        visit_id = visit.get("id")
        if visit_id is None:
            continue
        started, ended = visit_times_from_payload(visit)
        if _should_skip_for_geofence(db, visit, started, ended):
            skipped_geofence += 1
            payload = dict(visit)
            payload["_deduped_by_geofence"] = True
            upsert_raw_event(
                db,
                source=SOURCE,
                external_id=str(visit_id),
                started_at=started,
                ended_at=ended,
                payload=payload,
            )
            continue

        activity, _meta = classify_dawarich_visit(visit)
        if activity is None:
            skipped_unclassified += 1

        raw_id = upsert_raw_event(
            db,
            source=SOURCE,
            external_id=str(visit_id),
            started_at=started,
            ended_at=ended,
            payload=visit,
        )
        touched_ids.append(raw_id)

    db.commit()
    segments_written = rebuild_segments_for_raw_events(db, touched_ids)

    write_sync_state(
        db,
        account,
        last_sync_at=now.isoformat(),
        last_visit_count=len(visits),
        range_start=since.isoformat(),
        range_end=until.isoformat(),
    )

    logger.info(
        "Dawarich sync: visits=%s raw=%s segments=%s skipped_geofence=%s",
        len(visits),
        len(touched_ids),
        segments_written,
        skipped_geofence,
    )

    return {
        "visits_fetched": len(visits),
        "raw_upserted": len(touched_ids),
        "segments_written": segments_written,
        "skipped_geofence_overlap": skipped_geofence,
        "skipped_unclassified": skipped_unclassified,
        "since": since.isoformat(),
        "until": until.isoformat(),
    }


def sync_dawarich_yesterday(db: Session) -> dict[str, Any]:
    """Pull visits for the previous calendar day in USER_TIMEZONE."""
    settings = get_settings()
    tz = ZoneInfo(settings.user_timezone)
    today_local = datetime.now(tz).date()
    start_local = datetime.combine(today_local - timedelta(days=1), time.min, tzinfo=tz)
    end_local = datetime.combine(today_local, time.min, tzinfo=tz)
    return sync_dawarich(
        db,
        since=start_local.astimezone(timezone.utc),
        until=end_local.astimezone(timezone.utc),
    )
