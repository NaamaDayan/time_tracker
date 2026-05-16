from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import verify_api_key
from app.config import get_settings
from app.connectors.clockify.sync import sync_clockify
from app.connectors.google_calendar.sync import sync_google_calendar
from app.connectors.sync_all import sync_all_sources
from app.database import get_db
from app.models import ActivitySegment, ActivityType
from app.pipeline.aggregate import aggregate_segments
from app.schemas.aggregate import ActivityTypeOut, AggregateResponse, AggregateSlice
from app.schemas.sync import SyncRequest, SyncResponse
from app.schemas.timeline import SegmentOut, TimelineResponse

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/config")
def config() -> dict:
    settings = get_settings()
    return {"timezone": settings.user_timezone}


@router.get("/timeline", response_model=TimelineResponse)
def timeline(
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    db: Session = Depends(get_db),
) -> TimelineResponse:
    if from_.tzinfo is None:
        from_ = from_.replace(tzinfo=timezone.utc)
    if to.tzinfo is None:
        to = to.replace(tzinfo=timezone.utc)

    rows = (
        db.query(ActivitySegment, ActivityType)
        .join(ActivityType, ActivitySegment.activity_type_slug == ActivityType.slug)
        .filter(ActivitySegment.started_at < to, ActivitySegment.ended_at > from_)
        .order_by(ActivitySegment.started_at)
        .all()
    )
    segments = [
        SegmentOut(
            id=seg.id,
            started_at=seg.started_at,
            ended_at=seg.ended_at,
            activity_type=seg.activity_type_slug,
            activity_label=atype.label,
            color=atype.color,
            source=seg.source,
            confidence=seg.confidence,
            metadata=seg.metadata_,
        )
        for seg, atype in rows
    ]
    return TimelineResponse(
        from_=from_,
        to=to,
        segments=segments,
        timezone=get_settings().user_timezone,
    )


@router.get("/activity-types", response_model=list[ActivityTypeOut])
def list_activity_types(db: Session = Depends(get_db)) -> list[ActivityTypeOut]:
    types = db.query(ActivityType).order_by(ActivityType.label).all()
    return [ActivityTypeOut.model_validate(t) for t in types]


@router.get("/aggregate", response_model=AggregateResponse)
def aggregate(
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    types: str | None = Query(
        default=None,
        description="Comma-separated activity type slugs to include",
    ),
    db: Session = Depends(get_db),
) -> AggregateResponse:
    if from_.tzinfo is None:
        from_ = from_.replace(tzinfo=timezone.utc)
    if to.tzinfo is None:
        to = to.replace(tzinfo=timezone.utc)

    activity_filter = [t.strip() for t in types.split(",") if t.strip()] if types else None

    rows = (
        db.query(ActivitySegment, ActivityType)
        .join(ActivityType, ActivitySegment.activity_type_slug == ActivityType.slug)
        .filter(ActivitySegment.started_at < to, ActivitySegment.ended_at > from_)
        .all()
    )
    segment_dicts = [
        {
            "started_at": seg.started_at,
            "ended_at": seg.ended_at,
            "activity_type": seg.activity_type_slug,
            "activity_label": atype.label,
            "color": atype.color,
        }
        for seg, atype in rows
    ]
    result = aggregate_segments(
        segment_dicts,
        window_start=from_,
        window_end=to,
        activity_types=activity_filter,
    )
    return AggregateResponse(
        from_=from_,
        to=to,
        timezone=get_settings().user_timezone,
        total_seconds=result["total_seconds"],
        unattributed_seconds=result["unattributed_seconds"],
        slices=[AggregateSlice(**s) for s in result["slices"]],
    )


@router.post("/sync", response_model=SyncResponse)
def sync_all_endpoint(
    body: SyncRequest | None = None,
    db: Session = Depends(get_db),
) -> SyncResponse:
    since = body.since if body else "7d"
    result = sync_all_sources(db, since=since)
    clockify = result.get("sources", {}).get("clockify") or {}
    return SyncResponse(
        since=since,
        raw_upserted=result["raw_upserted"],
        segments_written=result["segments_written"],
        entries_fetched=result["entries_fetched"],
        sources=result["sources"],
        errors=result["errors"],
        workspace_id=clockify.get("workspace_id"),
    )


@router.post("/sync/google-calendar", response_model=SyncResponse)
def sync_google_calendar_endpoint(db: Session = Depends(get_db)) -> SyncResponse:
    result = sync_google_calendar(db)
    return SyncResponse(
        since="incremental",
        sources={"google_calendar": result},
        errors={},
        **{k: result[k] for k in ("raw_upserted", "segments_written", "entries_fetched")},
    )


@router.post("/sync/clockify", response_model=SyncResponse)
def sync_clockify_endpoint(
    body: SyncRequest | None = None,
    db: Session = Depends(get_db),
) -> SyncResponse:
    since = body.since if body else "7d"
    result = sync_clockify(db, since=since)
    return SyncResponse(
        since=since,
        sources={"clockify": result},
        errors={},
        **result,
    )
