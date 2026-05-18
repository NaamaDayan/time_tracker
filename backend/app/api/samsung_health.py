import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import verify_api_key
from app.config import get_settings
from app.connectors.samsung_health.schemas import SamsungHealthIngestBatch
from app.connectors.samsung_health.sync import SOURCE, sync_samsung_health_from_batch
from app.connectors.sync_state import read_sync_state
from app.database import get_db
from app.models import RawEvent, SourceAccount
from app.schemas.health import DailyHealthStat, HealthDailyStatsResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/integrations/samsung",
    tags=["integrations"],
    dependencies=[Depends(verify_api_key)],
)


def _get_account(db: Session) -> SourceAccount | None:
    return db.query(SourceAccount).filter(SourceAccount.source == SOURCE).first()


@router.get("/status")
def samsung_health_status(db: Session = Depends(get_db)) -> dict:
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
def samsung_health_ingest(
    batch: SamsungHealthIngestBatch,
    db: Session = Depends(get_db),
) -> dict:
    if batch.synced_at.tzinfo is None:
        batch.synced_at = batch.synced_at.replace(tzinfo=timezone.utc)
    result = sync_samsung_health_from_batch(db, batch)
    return {"ok": True, **result}


@router.get("/daily-stats", response_model=HealthDailyStatsResponse)
def samsung_health_daily_stats(
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    db: Session = Depends(get_db),
) -> HealthDailyStatsResponse:
    if from_.tzinfo is None:
        from_ = from_.replace(tzinfo=timezone.utc)
    if to.tzinfo is None:
        to = to.replace(tzinfo=timezone.utc)

    rows = (
        db.query(RawEvent)
        .filter(
            RawEvent.source == SOURCE,
            RawEvent.started_at < to,
            RawEvent.ended_at > from_,
        )
        .order_by(RawEvent.started_at)
        .all()
    )

    steps_by_date: dict[date, int] = {}
    calories_by_date: dict[date, float] = {}

    for row in rows:
        payload = row.payload or {}
        record_type = payload.get("record_type")
        if record_type == "daily_steps":
            local_date_str = payload.get("local_date")
            if not local_date_str:
                continue
            d = date.fromisoformat(local_date_str)
            count = payload.get("step_count")
            if count is not None:
                steps_by_date[d] = int(count)
        elif record_type == "exercise_session":
            local_d = row.started_at.date()
            cal = payload.get("calories")
            if cal is not None:
                calories_by_date[local_d] = calories_by_date.get(local_d, 0.0) + float(cal)

    all_dates = sorted(set(steps_by_date) | set(calories_by_date))
    days = [
        DailyHealthStat(
            local_date=d,
            step_count=steps_by_date.get(d),
            calories_burned=calories_by_date.get(d),
        )
        for d in all_dates
    ]

    return HealthDailyStatsResponse(
        from_=from_,
        to=to,
        timezone=get_settings().user_timezone,
        days=days,
    )
