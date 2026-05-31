from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.api.deps import verify_api_key
from app.config import get_settings
from app.connectors.activitywatch.desktop_sync import sync_activitywatch_desktop
from app.connectors.dawarich.sync import sync_dawarich
from app.connectors.google_calendar.sync import sync_google_calendar
from app.connectors.sync_all import sync_all_sources
from app.connectors.utils import parse_since
from app.database import get_db
from app.models import ActivitySegment, ActivityType
from app.pipeline.activity_priority import get_priority_ranks
from app.pipeline.aggregate import aggregate_segments
from app.pipeline.net import net_totals_segments
from app.pipeline.time_budget import calendar_days_in_range
from app.schemas.aggregate import ActivityTypeOut, AggregateResponse, AggregateSlice
from app.schemas.net import NetResponse, NetSlice
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
        .filter(
            ActivitySegment.started_at < to,
            or_(
                ActivitySegment.ended_at.is_(None),
                ActivitySegment.ended_at > from_,
            ),
        )
        .order_by(ActivitySegment.started_at)
        .all()
    )
    segments = [
        SegmentOut(
            id=seg.id,
            started_at=seg.started_at,
            ended_at=seg.ended_at if seg.ended_at is not None else to,
            activity_type=seg.activity_type_slug,
            activity_label=atype.label,
            color=atype.color,
            source=seg.source,
            confidence=seg.confidence,
            metadata=seg.metadata_,
        )
        for seg, atype in rows
        if not (seg.metadata_ or {}).get("exclude_from_windows")
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


@router.post("/activity-types", response_model=ActivityTypeOut, status_code=201)
def create_activity_type(
    body: ActivityTypeOut,
    db: Session = Depends(get_db),
) -> ActivityTypeOut:
    existing = db.query(ActivityType).filter(ActivityType.slug == body.slug).first()
    if existing:
        return ActivityTypeOut.model_validate(existing)
    atype = ActivityType(slug=body.slug, label=body.label, color=body.color)
    db.add(atype)
    db.commit()
    db.refresh(atype)
    return ActivityTypeOut.model_validate(atype)


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
        .filter(
            ActivitySegment.started_at < to,
            ActivitySegment.ended_at.isnot(None),
            ActivitySegment.ended_at > from_,
        )
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
        if not (seg.metadata_ or {}).get("exclude_from_windows")
    ]
    settings = get_settings()
    ranks = get_priority_ranks(db)
    result = aggregate_segments(
        segment_dicts,
        window_start=from_,
        window_end=to,
        activity_types=activity_filter,
        timezone_name=settings.user_timezone,
        priority_ranks=ranks,
    )
    return AggregateResponse(
        from_=from_,
        to=to,
        timezone=settings.user_timezone,
        calendar_days=result["calendar_days"],
        total_seconds=result["total_seconds"],
        unattributed_seconds=result["unattributed_seconds"],
        slices=[AggregateSlice(**s) for s in result["slices"]],
    )


@router.get("/net", response_model=NetResponse)
def net_totals(
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    types: str | None = Query(
        default=None,
        description="Comma-separated activity type slugs to include",
    ),
    db: Session = Depends(get_db),
) -> NetResponse:
    if from_.tzinfo is None:
        from_ = from_.replace(tzinfo=timezone.utc)
    if to.tzinfo is None:
        to = to.replace(tzinfo=timezone.utc)

    activity_filter = [t.strip() for t in types.split(",") if t.strip()] if types else None

    rows = (
        db.query(ActivitySegment, ActivityType)
        .join(ActivityType, ActivitySegment.activity_type_slug == ActivityType.slug)
        .filter(
            ActivitySegment.started_at < to,
            ActivitySegment.ended_at.isnot(None),
            ActivitySegment.ended_at > from_,
        )
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
        if not (seg.metadata_ or {}).get("exclude_from_windows")
    ]
    settings = get_settings()
    calendar_days = calendar_days_in_range(
        from_, to, timezone_name=settings.user_timezone
    )
    result = net_totals_segments(
        segment_dicts,
        window_start=from_,
        window_end=to,
        activity_types=activity_filter,
    )
    return NetResponse(
        from_=from_,
        to=to,
        timezone=settings.user_timezone,
        calendar_days=calendar_days,
        total_seconds=result["total_seconds"],
        slices=[NetSlice(**s) for s in result["slices"]],
    )


@router.post("/sync", response_model=SyncResponse)
def sync_all_endpoint(
    body: SyncRequest | None = None,
    db: Session = Depends(get_db),
) -> SyncResponse:
    since = body.since if body else "7d"
    result = sync_all_sources(db, since=since)
    return SyncResponse(
        since=since,
        raw_upserted=result["raw_upserted"],
        segments_written=result["segments_written"],
        entries_fetched=result["entries_fetched"],
        sources=result["sources"],
        errors=result["errors"],
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


@router.post("/sync/dawarich", response_model=SyncResponse)
def sync_dawarich_endpoint(
    body: SyncRequest | None = None,
    db: Session = Depends(get_db),
) -> SyncResponse:
    since = body.since if body else "2d"
    result = sync_dawarich(db, since=parse_since(since))
    return SyncResponse(
        since=since,
        sources={"dawarich": result},
        errors={},
        raw_upserted=result.get("raw_upserted", 0),
        segments_written=result.get("segments_written", 0),
        entries_fetched=result.get("visits_fetched", 0),
    )


@router.post("/sync/activitywatch-desktop", response_model=SyncResponse)
def sync_activitywatch_desktop_endpoint(
    body: SyncRequest | None = None,
    db: Session = Depends(get_db),
) -> SyncResponse:
    since = body.since if body else "7d"
    result = sync_activitywatch_desktop(db, since=since)
    return SyncResponse(
        since=since,
        sources={"activitywatch_desktop": result},
        errors={},
        raw_upserted=result.get("raw_upserted", 0),
        segments_written=result.get("segments_written", 0),
        entries_fetched=result.get("entries_fetched", 0),
    )
