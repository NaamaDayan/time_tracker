from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import ActivitySegment, RawEvent, SourceAccount


def read_sync_state(account: SourceAccount | None) -> dict[str, Any]:
    if not account or not account.config_json:
        return {}
    return dict(account.config_json)


def write_sync_state(db: Session, account: SourceAccount, **fields: Any) -> None:
    config = dict(account.config_json or {})
    config.update(fields)
    account.config_json = config
    db.commit()


def upsert_raw_event(
    db: Session,
    *,
    source: str,
    external_id: str,
    started_at: datetime,
    ended_at: datetime,
    payload: dict[str, Any],
) -> int:
    now = datetime.now(timezone.utc)
    existing = (
        db.query(RawEvent)
        .filter(RawEvent.source == source, RawEvent.external_id == external_id)
        .first()
    )
    if existing:
        existing.started_at = started_at
        existing.ended_at = ended_at
        existing.payload = payload
        db.flush()
        return existing.id

    raw = RawEvent(
        source=source,
        external_id=external_id,
        started_at=started_at,
        ended_at=ended_at,
        payload=payload,
        ingested_at=now,
    )
    db.add(raw)
    db.flush()
    return raw.id


def delete_raw_event(db: Session, *, source: str, external_id: str) -> int | None:
    existing = (
        db.query(RawEvent)
        .filter(RawEvent.source == source, RawEvent.external_id == external_id)
        .first()
    )
    if not existing:
        return None
    raw_id = existing.id
    db.execute(delete(ActivitySegment).where(ActivitySegment.raw_event_id == raw_id))
    db.delete(existing)
    db.flush()
    return raw_id
