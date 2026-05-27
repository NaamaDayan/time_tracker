from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import verify_api_key
from app.config import get_settings
from app.database import get_db
from app.models import ActivitySegment, ActivityType, ActivityWindow, ActivityWindowSegment
from app.schemas.windows import WindowOut, WindowsResponse

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])


@router.get("/windows", response_model=WindowsResponse)
def list_windows(
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    db: Session = Depends(get_db),
) -> WindowsResponse:
    if from_.tzinfo is None:
        from_ = from_.replace(tzinfo=timezone.utc)
    if to.tzinfo is None:
        to = to.replace(tzinfo=timezone.utc)

    rows = (
        db.query(ActivityWindow, ActivityType)
        .join(ActivityType, ActivityWindow.activity_type_slug == ActivityType.slug)
        .filter(ActivityWindow.started_at < to, ActivityWindow.ended_at > from_)
        .order_by(ActivityWindow.started_at)
        .all()
    )

    window_ids = [win.id for win, _ in rows]
    segment_ids_by_window: dict[int, list[int]] = {wid: [] for wid in window_ids}
    segment_meta_by_window: dict[int, dict] = {}
    if window_ids:
        links = (
            db.query(ActivityWindowSegment)
            .filter(ActivityWindowSegment.window_id.in_(window_ids))
            .all()
        )
        all_seg_ids = [link.segment_id for link in links]
        segments_by_id: dict[int, ActivitySegment] = {}
        if all_seg_ids:
            segments_by_id = {
                s.id: s
                for s in db.query(ActivitySegment)
                .filter(ActivitySegment.id.in_(all_seg_ids))
                .all()
            }
        for link in links:
            segment_ids_by_window[link.window_id].append(link.segment_id)
            seg = segments_by_id.get(link.segment_id)
            if seg and seg.source == "samsung_health" and link.window_id not in segment_meta_by_window:
                segment_meta_by_window[link.window_id] = dict(seg.metadata_ or {})
        for wid in segment_ids_by_window:
            segment_ids_by_window[wid].sort()

    gap_minutes = get_settings().activity_merge_gap_minutes
    min_duration_seconds = gap_minutes * 60

    windows = []
    for win, atype in rows:
        duration = (win.ended_at - win.started_at).total_seconds()
        if duration < min_duration_seconds:
            continue
        windows.append(
            WindowOut(
                id=win.id,
                started_at=win.started_at,
                ended_at=win.ended_at,
                activity_type=win.activity_type_slug,
                activity_label=atype.label,
                color=atype.color,
                confidence=win.confidence,
                sources=list(win.sources) if win.sources else [],
                segment_ids=segment_ids_by_window.get(win.id, []),
                metadata={**(win.metadata_ or {}), **segment_meta_by_window.get(win.id, {})},
            )
        )

    return WindowsResponse(
        from_=from_,
        to=to,
        windows=windows,
        timezone=get_settings().user_timezone,
    )
