from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import verify_api_key
from app.database import get_db
from app.models import ActivitySegment, ActivityType
from app.pipeline.windows.service import recompute_windows_after_segment_change
from app.schemas.segment import SegmentCreate, SegmentMutationOut, SegmentUpdate

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])

MANUAL_SOURCE = "manual"


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _all_day_range(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Store all-day events as UTC midnight through end-of-day (inclusive display)."""
    start_d = _ensure_utc(start).date()
    end_d = _ensure_utc(end).date()
    if end_d < start_d:
        end_d = start_d
    started = datetime(start_d.year, start_d.month, start_d.day, tzinfo=timezone.utc)
    ended = datetime(end_d.year, end_d.month, end_d.day, 23, 59, 59, tzinfo=timezone.utc)
    return started, ended


def _segment_to_out(seg: ActivitySegment, atype: ActivityType) -> SegmentMutationOut:
    return SegmentMutationOut(
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


def _get_manual_segment(db: Session, segment_id: int) -> tuple[ActivitySegment, ActivityType]:
    row = (
        db.query(ActivitySegment, ActivityType)
        .join(ActivityType, ActivitySegment.activity_type_slug == ActivityType.slug)
        .filter(ActivitySegment.id == segment_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Segment not found")
    seg, atype = row
    if seg.source != MANUAL_SOURCE:
        raise HTTPException(status_code=403, detail="Only manual events can be edited or deleted")
    return seg, atype


@router.post("/segments", response_model=SegmentMutationOut)
def create_segment(body: SegmentCreate, db: Session = Depends(get_db)) -> SegmentMutationOut:
    atype = db.query(ActivityType).filter(ActivityType.slug == body.activity_type).first()
    if not atype:
        raise HTTPException(status_code=400, detail=f"Unknown activity type: {body.activity_type}")

    started = _ensure_utc(body.started_at)
    ended = _ensure_utc(body.ended_at)
    if body.all_day:
        started, ended = _all_day_range(started, ended)
    elif ended <= started:
        raise HTTPException(status_code=400, detail="ended_at must be after started_at")

    metadata: dict = {"title": body.title} if body.title else {}
    if body.all_day:
        metadata["is_all_day"] = True

    seg = ActivitySegment(
        started_at=started,
        ended_at=ended,
        activity_type_slug=body.activity_type,
        source=MANUAL_SOURCE,
        source_manual=True,
        confidence=1.0,
        metadata_=metadata or None,
        raw_event_id=None,
    )
    db.add(seg)
    db.flush()
    recompute_windows_after_segment_change(db, segment_ids=[seg.id])
    db.commit()
    db.refresh(seg)
    return _segment_to_out(seg, atype)


@router.patch("/segments/{segment_id}", response_model=SegmentMutationOut)
def update_segment(
    segment_id: int,
    body: SegmentUpdate,
    db: Session = Depends(get_db),
) -> SegmentMutationOut:
    seg, atype = _get_manual_segment(db, segment_id)
    old_type_slug = seg.activity_type_slug
    old_snapshot = ActivitySegment(
        started_at=seg.started_at,
        ended_at=seg.ended_at,
        activity_type_slug=old_type_slug,
        source=seg.source,
        confidence=seg.confidence,
        raw_event_id=seg.raw_event_id,
    )
    old_snapshot.id = seg.id

    started = _ensure_utc(body.started_at) if body.started_at else _ensure_utc(seg.started_at)
    ended = _ensure_utc(body.ended_at) if body.ended_at else _ensure_utc(seg.ended_at)
    all_day = body.all_day if body.all_day is not None else bool((seg.metadata_ or {}).get("is_all_day"))

    if body.all_day is True or (all_day and (body.started_at or body.ended_at)):
        started, ended = _all_day_range(started, ended)
    elif not all_day and ended <= started:
        raise HTTPException(status_code=400, detail="ended_at must be after started_at")

    if body.activity_type:
        new_type = db.query(ActivityType).filter(ActivityType.slug == body.activity_type).first()
        if not new_type:
            raise HTTPException(status_code=400, detail=f"Unknown activity type: {body.activity_type}")
        seg.activity_type_slug = body.activity_type
        atype = new_type

    seg.started_at = started
    seg.ended_at = ended

    metadata = dict(seg.metadata_ or {})
    if body.title is not None:
        if body.title:
            metadata["title"] = body.title
        else:
            metadata.pop("title", None)
    if body.all_day is not None:
        metadata["is_all_day"] = body.all_day
    seg.metadata_ = metadata or None

    extra_types: set[str] = set()
    if seg.activity_type_slug != old_type_slug:
        extra_types.add(old_type_slug)
    recompute_windows_after_segment_change(
        db,
        segment_ids=[seg.id],
        extra_types=extra_types,
        bounds_from_segments=[old_snapshot, seg],
    )
    db.commit()
    db.refresh(seg)
    return _segment_to_out(seg, atype)


@router.delete("/segments/{segment_id}", status_code=204)
def delete_segment(segment_id: int, db: Session = Depends(get_db)) -> None:
    seg, _ = _get_manual_segment(db, segment_id)
    snapshot = ActivitySegment(
        started_at=seg.started_at,
        ended_at=seg.ended_at,
        activity_type_slug=seg.activity_type_slug,
        source=seg.source,
        confidence=seg.confidence,
        raw_event_id=seg.raw_event_id,
    )
    snapshot.id = seg.id
    db.delete(seg)
    db.flush()
    recompute_windows_after_segment_change(
        db, bounds_from_segments=[snapshot]
    )
    db.commit()
