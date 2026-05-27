import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.activitywatch.schemas import ActivityWatchIngestBatch, ActivityWatchRecordIn
from app.connectors.sync_state import read_sync_state, upsert_raw_event, write_sync_state
from app.models import SourceAccount
from app.pipeline.normalize import rebuild_segments_for_raw_events

logger = logging.getLogger(__name__)

SOURCE = "activitywatch"


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _build_payload(record: ActivityWatchRecordIn) -> dict[str, Any]:
    payload = dict(record.payload)
    payload["record_type"] = record.record_type
    if record.started_at is not None:
        payload["started_at"] = _ensure_utc(record.started_at).isoformat()
    if record.ended_at is not None:
        payload["ended_at"] = _ensure_utc(record.ended_at).isoformat()
    return payload


def _times_for_record(record: ActivityWatchRecordIn) -> tuple[datetime, datetime]:
    if record.started_at is None or record.ended_at is None:
        raise ValueError(
            f"{record.record_type} record {record.external_id} requires started_at and ended_at"
        )
    started = _ensure_utc(record.started_at)
    ended = _ensure_utc(record.ended_at)
    if ended <= started:
        ended = started + timedelta(seconds=1)
    return started, ended


def _get_or_create_account(db: Session) -> SourceAccount:
    account = db.query(SourceAccount).filter(SourceAccount.source == SOURCE).first()
    if not account:
        account = SourceAccount(
            source=SOURCE,
            display_name="Activity Watch",
            config_json={},
            is_active=True,
        )
        db.add(account)
        db.flush()
    return account


def sync_activitywatch_from_batch(
    db: Session,
    batch: ActivityWatchIngestBatch,
) -> dict[str, Any]:
    """Upsert raw events from Android companion Activity Watch ingest batch."""
    account = _get_or_create_account(db)
    touched_ids: list[int] = []
    by_type: dict[str, int] = {}

    for record in batch.records:
        started_at, ended_at = _times_for_record(record)
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
        "Activity Watch ingest: records=%s raw=%s segments=%s device=%s",
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
