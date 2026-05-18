import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors.samsung_health.schemas import SamsungHealthIngestBatch, SamsungHealthRecordIn
from app.connectors.sync_state import read_sync_state, upsert_raw_event, write_sync_state
from app.models import SourceAccount
from app.pipeline.normalize import rebuild_segments_for_raw_events

logger = logging.getLogger(__name__)

SOURCE = "samsung_health"


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _day_bounds_utc(local_date: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(local_date, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _build_payload(record: SamsungHealthRecordIn) -> dict[str, Any]:
    payload = dict(record.payload)
    payload["record_type"] = record.record_type
    if record.step_count is not None:
        payload["step_count"] = record.step_count
    if record.local_date is not None:
        payload["local_date"] = record.local_date.isoformat()
    if record.started_at is not None:
        payload["started_at"] = _ensure_utc(record.started_at).isoformat()
    if record.ended_at is not None:
        payload["ended_at"] = _ensure_utc(record.ended_at).isoformat()
    return payload


def _times_for_record(
    record: SamsungHealthRecordIn,
    *,
    tz_name: str,
) -> tuple[datetime, datetime]:
    if record.record_type == "daily_steps":
        if record.local_date is None:
            raise ValueError(f"daily_steps record {record.external_id} missing local_date")
        return _day_bounds_utc(record.local_date, tz_name)

    if record.started_at is None or record.ended_at is None:
        raise ValueError(
            f"{record.record_type} record {record.external_id} requires started_at and ended_at"
        )
    started = _ensure_utc(record.started_at)
    ended = _ensure_utc(record.ended_at)
    if ended <= started:
        ended = started + timedelta(minutes=1)
    return started, ended


def _get_or_create_account(db: Session) -> SourceAccount:
    account = db.query(SourceAccount).filter(SourceAccount.source == SOURCE).first()
    if not account:
        account = SourceAccount(
            source=SOURCE,
            display_name="Samsung Health",
            config_json={},
            is_active=True,
        )
        db.add(account)
        db.flush()
    return account


def sync_samsung_health_from_batch(
    db: Session,
    batch: SamsungHealthIngestBatch,
) -> dict[str, Any]:
    """Upsert raw events from Android companion ingest batch."""
    account = _get_or_create_account(db)
    tz_name = get_settings().user_timezone
    touched_ids: list[int] = []
    by_type: dict[str, int] = {}

    for record in batch.records:
        started_at, ended_at = _times_for_record(record, tz_name=tz_name)
        payload = _build_payload(record)
        raw_id = upsert_raw_event(
            db,
            source=SOURCE,
            external_id=record.external_id,
            started_at=started_at,
            ended_at=ended_at,
            payload=payload,
        )
        touched_ids.append(raw_id)
        by_type[record.record_type] = by_type.get(record.record_type, 0) + 1

    db.commit()
    segments_written = rebuild_segments_for_raw_events(db, touched_ids)

    write_sync_state(
        db,
        account,
        last_sync_at=batch.synced_at.isoformat(),
        device_id=batch.device_id,
        last_record_counts=by_type,
    )

    logger.info(
        "Samsung Health ingest: records=%s raw=%s segments=%s device=%s",
        len(batch.records),
        len(touched_ids),
        segments_written,
        batch.device_id,
    )

    return {
        "raw_upserted": len(touched_ids),
        "segments_written": segments_written,
        "records_by_type": by_type,
        "device_id": batch.device_id,
    }
