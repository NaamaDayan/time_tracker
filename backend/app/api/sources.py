import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import verify_api_key
from app.database import get_db
from app.models import ActivitySegment, RawEvent, SourceAccount

logger = logging.getLogger(__name__)

ALLOWED_PURGE_SOURCES = frozenset({"geofence", "dawarich", "activitywatch", "samsung_health"})

router = APIRouter(
    prefix="/api/v1/sources",
    tags=["sources"],
    dependencies=[Depends(verify_api_key)],
)


@router.delete("/{source}/data")
def purge_source_data(source: str, db: Session = Depends(get_db)) -> dict:
    """Delete all raw events and segments for a source (privacy / reset)."""
    if source not in ALLOWED_PURGE_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Source not allowed for purge: {source}. Allowed: {sorted(ALLOWED_PURGE_SOURCES)}",
        )

    raw_ids = [
        row[0]
        for row in db.query(RawEvent.id).filter(RawEvent.source == source).all()
    ]
    segments_deleted = (
        db.query(ActivitySegment)
        .filter(ActivitySegment.source == source)
        .delete(synchronize_session=False)
    )
    raw_deleted = (
        db.query(RawEvent).filter(RawEvent.source == source).delete(synchronize_session=False)
    )
    account = db.query(SourceAccount).filter(SourceAccount.source == source).first()
    if account:
        account.config_json = {}
    db.commit()

    logger.info(
        "Purged source=%s raw=%s segments=%s",
        source,
        raw_deleted,
        segments_deleted,
    )
    return {
        "ok": True,
        "source": source,
        "raw_deleted": raw_deleted,
        "segments_deleted": segments_deleted,
        "raw_ids": raw_ids,
    }
