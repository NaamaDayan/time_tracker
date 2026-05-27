import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import verify_api_key
from app.connectors.activitywatch.schemas import ActivityWatchIngestBatch
from app.connectors.activitywatch.sync import SOURCE, sync_activitywatch_from_batch
from app.connectors.sync_state import read_sync_state
from app.database import get_db
from app.models import SourceAccount

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/integrations/activitywatch",
    tags=["integrations"],
    dependencies=[Depends(verify_api_key)],
)


def _get_account(db: Session) -> SourceAccount | None:
    return db.query(SourceAccount).filter(SourceAccount.source == SOURCE).first()


@router.get("/status")
def activitywatch_status(db: Session = Depends(get_db)) -> dict:
    account = _get_account(db)
    if not account:
        return {
            "connected": False,
            "last_sync_at": None,
            "device_id": None,
            "last_record_counts": None,
        }
    state = read_sync_state(account)
    return {
        "connected": True,
        "last_sync_at": state.get("last_sync_at"),
        "device_id": state.get("device_id"),
        "last_record_counts": state.get("last_record_counts"),
    }


@router.post("/ingest")
def activitywatch_ingest(
    batch: ActivityWatchIngestBatch,
    db: Session = Depends(get_db),
) -> dict:
    if batch.synced_at.tzinfo is None:
        batch.synced_at = batch.synced_at.replace(tzinfo=timezone.utc)
    result = sync_activitywatch_from_batch(db, batch)
    return {"ok": True, **result}
