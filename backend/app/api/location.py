import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import verify_api_key
from app.config import get_settings
from app.connectors.geofence.sync import SOURCE as GEOFENCE_SOURCE, handle_geofence_event
from app.connectors.sync_state import read_sync_state
from app.database import get_db
from app.models import SourceAccount
from app.connectors.geofence.schemas import GeofenceEventIn

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/integrations/location",
    tags=["integrations", "location"],
    dependencies=[Depends(verify_api_key)],
)


def _get_account(db: Session, source: str) -> SourceAccount | None:
    return db.query(SourceAccount).filter(SourceAccount.source == source).first()


@router.get("/status")
def location_status(db: Session = Depends(get_db)) -> dict:
    geofence = _get_account(db, GEOFENCE_SOURCE)
    dawarich = _get_account(db, "dawarich")
    settings = get_settings()
    geo_state = read_sync_state(geofence) if geofence else {}
    dw_state = read_sync_state(dawarich) if dawarich else {}
    return {
        "geofence": {
            "connected": geofence is not None and geofence.is_active,
            "last_event_at": geo_state.get("last_event_at"),
            "last_zone": geo_state.get("last_zone"),
            "last_transition": geo_state.get("last_transition"),
        },
        "dawarich": {
            "sync_enabled": settings.dawarich_sync_enabled,
            "base_url": settings.dawarich_base_url or None,
            "last_sync_at": dw_state.get("last_sync_at"),
            "last_visit_count": dw_state.get("last_visit_count"),
        },
    }


@router.post("/geofence")
def geofence_ingest(
    event: GeofenceEventIn,
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    if not settings.location_geofence_enabled:
        raise HTTPException(status_code=503, detail="Geofence ingest is disabled")
    if event.timestamp.tzinfo is None:
        event.timestamp = event.timestamp.replace(tzinfo=timezone.utc)
    result = handle_geofence_event(db, event)
    return {"ok": True, **result}
