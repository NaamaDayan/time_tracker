from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import verify_api_key
from app.api.window_corrections import (
    MANUAL_SOURCE,
    confirm_window,
    create_manual_segment,
    dismiss_window,
    find_covering_window,
    recompute_for_manual_segment,
    undelete_original_correction,
    validate_activity_type,
    validate_manual_duration,
    _segment_ids_for_window,
)
from app.config import get_settings
from app.database import get_db
from app.models import ActivitySegment, ActivityType, ActivityWindow, ActivityWindowSegment
from app.schemas.windows import ManualWindowCreate, WindowOut, WindowPatch, WindowsResponse

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_segment_maps(
    db: Session, window_ids: list[int]
) -> tuple[dict[int, list[int]], dict[int, dict]]:
    segment_ids_by_window: dict[int, list[int]] = {wid: [] for wid in window_ids}
    segment_meta_by_window: dict[int, dict] = {}
    if not window_ids:
        return segment_ids_by_window, segment_meta_by_window

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
    return segment_ids_by_window, segment_meta_by_window


def _window_to_out(
    win: ActivityWindow,
    atype: ActivityType,
    segment_ids: list[int],
    segment_meta: dict | None = None,
) -> WindowOut:
    return WindowOut(
        id=win.id,
        started_at=win.started_at,
        ended_at=win.ended_at,
        activity_type=win.activity_type_slug,
        activity_label=atype.label,
        color=atype.color,
        confidence=win.confidence,
        sources=list(win.sources) if win.sources else [],
        segment_ids=segment_ids,
        segment_count=win.segment_count,
        confirmed_by_user=win.confirmed_by_user,
        dismissed_by_user=win.dismissed_by_user,
        correction_of_window_id=win.correction_of_window_id,
        metadata={**(win.metadata_ or {}), **(segment_meta or {})},
    )


def _get_window_row(db: Session, window_id: int) -> tuple[ActivityWindow, ActivityType]:
    row = (
        db.query(ActivityWindow, ActivityType)
        .join(ActivityType, ActivityWindow.activity_type_slug == ActivityType.slug)
        .filter(ActivityWindow.id == window_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Window not found")
    return row


@router.get("/windows", response_model=WindowsResponse)
def list_windows(
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    include_dismissed: bool = Query(default=False),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
) -> WindowsResponse:
    from_ = _ensure_utc(from_)
    to = _ensure_utc(to)

    q = (
        db.query(ActivityWindow, ActivityType)
        .join(ActivityType, ActivityWindow.activity_type_slug == ActivityType.slug)
        .filter(
            ActivityWindow.started_at < to,
            ActivityWindow.ended_at > from_,
            ActivityWindow.confidence >= min_confidence,
        )
    )
    if not include_dismissed:
        q = q.filter(ActivityWindow.dismissed_by_user.is_(False))

    rows = q.order_by(ActivityWindow.started_at).all()

    window_ids = [win.id for win, _ in rows]
    segment_ids_by_window, segment_meta_by_window = _load_segment_maps(db, window_ids)

    gap_minutes = get_settings().activity_merge_gap_minutes
    min_duration_seconds = gap_minutes * 60

    windows = []
    for win, atype in rows:
        duration = (win.ended_at - win.started_at).total_seconds()
        is_manual_correction = win.correction_of_window_id is not None
        has_manual_segment = False
        seg_ids = segment_ids_by_window.get(win.id, [])
        if seg_ids:
            manual_count = (
                db.query(ActivitySegment)
                .filter(
                    ActivitySegment.id.in_(seg_ids),
                    ActivitySegment.source_manual.is_(True),
                )
                .count()
            )
            has_manual_segment = manual_count > 0
        if duration < min_duration_seconds and not is_manual_correction and not has_manual_segment:
            continue
        windows.append(
            _window_to_out(
                win,
                atype,
                seg_ids,
                segment_meta_by_window.get(win.id),
            )
        )

    return WindowsResponse(
        from_=from_,
        to=to,
        windows=windows,
        timezone=get_settings().user_timezone,
    )


@router.patch("/windows/{window_id}", response_model=WindowOut)
def patch_window(
    window_id: int,
    body: WindowPatch,
    db: Session = Depends(get_db),
) -> WindowOut:
    win, atype = _get_window_row(db, window_id)
    original_id = win.id
    original_started = win.started_at
    original_ended = win.ended_at
    original_slug = win.activity_type_slug

    type_change = (
        body.activity_type_slug is not None
        and body.activity_type_slug != win.activity_type_slug
    )

    if body.confirmed_by_user and not type_change:
        confirm_window(db, win)
        db.commit()
        db.refresh(win)
        seg_ids = _segment_ids_for_window(db, win.id)
        return _window_to_out(win, atype, seg_ids)

    if body.dismissed_by_user and not type_change:
        dismiss_window(db, win)
        db.commit()
        db.refresh(win)
        seg_ids = _segment_ids_for_window(db, win.id)
        return _window_to_out(win, atype, seg_ids)

    if type_change:
        validate_activity_type(db, body.activity_type_slug)
        dismiss_window(db, win)
        seg = create_manual_segment(
            db,
            activity_type_slug=body.activity_type_slug,
            started_at=original_started,
            ended_at=original_ended,
            note=None,
        )
        recompute_for_manual_segment(
            db,
            seg,
            extra_types={original_slug},
        )
        new_win = find_covering_window(
            db,
            activity_type_slug=body.activity_type_slug,
            started_at=original_started,
            ended_at=original_ended,
        )
        if new_win is None:
            db.commit()
            raise HTTPException(status_code=500, detail="Failed to create correction window")
        new_win.correction_of_window_id = original_id
        new_win.confidence = 1.0
        db.commit()
        db.refresh(new_win)
        _, new_atype = _get_window_row(db, new_win.id)
        seg_ids = _segment_ids_for_window(db, new_win.id)
        return _window_to_out(new_win, new_atype, seg_ids)

    db.commit()
    db.refresh(win)
    seg_ids = _segment_ids_for_window(db, win.id)
    return _window_to_out(win, atype, seg_ids)


@router.post("/windows/manual", response_model=WindowOut)
def create_manual_window(
    body: ManualWindowCreate,
    db: Session = Depends(get_db),
) -> WindowOut:
    atype = validate_activity_type(db, body.activity_type_slug)
    validate_manual_duration(db, body.activity_type_slug, body.started_at, body.ended_at)
    seg = create_manual_segment(
        db,
        activity_type_slug=body.activity_type_slug,
        started_at=body.started_at,
        ended_at=body.ended_at,
        note=body.note,
    )
    recompute_for_manual_segment(db, seg)
    db.commit()

    new_win = find_covering_window(
        db,
        activity_type_slug=body.activity_type_slug,
        started_at=body.started_at,
        ended_at=body.ended_at,
    )
    if new_win is None:
        raise HTTPException(status_code=500, detail="Failed to create window from manual segment")
    db.refresh(new_win)
    seg_ids = _segment_ids_for_window(db, new_win.id)
    return _window_to_out(new_win, atype, seg_ids)


@router.delete("/windows/manual/{window_id}", status_code=204)
def delete_manual_window(window_id: int, db: Session = Depends(get_db)) -> None:
    win, _ = _get_window_row(db, window_id)
    seg_ids = _segment_ids_for_window(db, window_id)
    if not seg_ids:
        raise HTTPException(status_code=400, detail="Window has no segments")

    segments = db.query(ActivitySegment).filter(ActivitySegment.id.in_(seg_ids)).all()
    is_correction = win.correction_of_window_id is not None
    all_manual = all(s.source_manual for s in segments)

    if not is_correction and not all_manual:
        raise HTTPException(
            status_code=403,
            detail="Only correction windows or all-manual windows can be deleted",
        )

    original_id = win.correction_of_window_id
    affected_types = {s.activity_type_slug for s in segments}
    bounds_segments = list(segments)

    for seg in segments:
        if is_correction and not seg.source_manual:
            continue
        if not seg.source_manual and not all_manual:
            continue
        db.delete(seg)
    db.flush()

    if original_id is not None:
        undelete_original_correction(db, original_id)
        orig = db.get(ActivityWindow, original_id)
        if orig:
            affected_types.add(orig.activity_type_slug)

    from app.pipeline.windows.service import recompute_windows_after_segment_change as recompute_fn

    recompute_fn(
        db,
        bounds_from_segments=bounds_segments,
        extra_types=affected_types,
    )
    db.commit()
