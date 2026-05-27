import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.activitywatch.client import ActivityWatchClient
from app.connectors.sync_state import upsert_raw_event, write_sync_state
from app.connectors.utils import parse_since
from app.models import SourceAccount
from app.pipeline.normalize import rebuild_segments_for_raw_events

logger = logging.getLogger(__name__)

SOURCE = "activitywatch_desktop"


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_aw_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _filter_not_afk(
    window_events: list[dict[str, Any]],
    afk_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep only window event portions that overlap with not-afk periods."""
    if not afk_events:
        return window_events

    not_afk_intervals: list[tuple[datetime, datetime]] = []
    for ev in afk_events:
        data = ev.get("data") or {}
        if data.get("status") != "not-afk":
            continue
        start = _parse_aw_timestamp(ev["timestamp"])
        dur = ev.get("duration", 0)
        end = start + timedelta(seconds=dur)
        not_afk_intervals.append((start, end))

    if not not_afk_intervals:
        return []

    not_afk_intervals.sort()

    filtered: list[dict[str, Any]] = []
    for ev in window_events:
        ev_start = _parse_aw_timestamp(ev["timestamp"])
        ev_dur = ev.get("duration", 0)
        ev_end = ev_start + timedelta(seconds=ev_dur)

        for naf_start, naf_end in not_afk_intervals:
            overlap_start = max(ev_start, naf_start)
            overlap_end = min(ev_end, naf_end)
            if overlap_start < overlap_end:
                clipped = dict(ev)
                clipped["timestamp"] = overlap_start.isoformat()
                clipped["duration"] = (overlap_end - overlap_start).total_seconds()
                clipped["_original_id"] = ev.get("id")
                filtered.append(clipped)

    return filtered


def _get_or_create_account(db: Session) -> SourceAccount:
    account = db.query(SourceAccount).filter(SourceAccount.source == SOURCE).first()
    if not account:
        account = SourceAccount(
            source=SOURCE,
            display_name="ActivityWatch Desktop",
            config_json={},
            is_active=True,
        )
        db.add(account)
        db.flush()
    return account


def sync_activitywatch_desktop(
    db: Session,
    *,
    since: str = "7d",
    start: datetime | None = None,
    end: datetime | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if end is None:
        end = now
    if start is None:
        start = end - parse_since(since)

    start = _ensure_utc(start)
    end = _ensure_utc(end)

    client = ActivityWatchClient(base_url=base_url)

    window_bucket = client.find_window_bucket()
    if not window_bucket:
        raise RuntimeError(
            "No aw-watcher-window bucket found. "
            "Is ActivityWatch running on this machine?"
        )

    logger.info(
        "ActivityWatch Desktop sync starting (bucket=%s, range=%s .. %s)",
        window_bucket,
        start.isoformat(),
        end.isoformat(),
    )

    window_events = client.get_events(window_bucket, start=start, end=end)

    afk_bucket = client.find_afk_bucket()
    if afk_bucket:
        afk_events = client.get_events(afk_bucket, start=start, end=end)
        events = _filter_not_afk(window_events, afk_events)
        logger.info(
            "AFK filtering: %d window events -> %d active events",
            len(window_events),
            len(events),
        )
    else:
        logger.warning("No aw-watcher-afk bucket found; using all window events")
        events = window_events

    account = _get_or_create_account(db)
    touched_ids: list[int] = []

    for ev in events:
        ev_start = _parse_aw_timestamp(ev["timestamp"])
        dur = ev.get("duration", 0)
        ev_end = ev_start + timedelta(seconds=dur)
        if ev_end <= ev_start:
            ev_end = ev_start + timedelta(seconds=1)

        external_id = str(ev.get("id") or ev.get("_original_id") or f"{window_bucket}:{ev['timestamp']}")

        data = ev.get("data") or {}
        payload = {
            "app": data.get("app"),
            "title": data.get("title"),
            "bucket_id": window_bucket,
            "aw_event_id": ev.get("id"),
            "duration": dur,
        }

        raw_id = upsert_raw_event(
            db,
            source=SOURCE,
            external_id=external_id,
            started_at=ev_start,
            ended_at=ev_end,
            payload=payload,
        )
        touched_ids.append(raw_id)

    db.commit()
    segments_written = rebuild_segments_for_raw_events(db, touched_ids)

    write_sync_state(
        db,
        account,
        last_sync_at=now.isoformat(),
        window_bucket=window_bucket,
        afk_bucket=afk_bucket,
    )

    logger.info(
        "ActivityWatch Desktop sync done: raw=%d segments=%d",
        len(touched_ids),
        segments_written,
    )

    return {
        "raw_upserted": len(touched_ids),
        "segments_written": segments_written,
        "entries_fetched": len(window_events),
        "window_bucket": window_bucket,
        "afk_bucket": afk_bucket,
    }
