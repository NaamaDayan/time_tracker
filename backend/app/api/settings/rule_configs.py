from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import verify_api_key
from app.database import get_db
from app.models import ActivityRuleConfig, ActivitySegment
from app.pipeline.rule_config import invalidate_rule_config_cache
from app.schemas.activity_rule_config import (
    ActivityRuleConfigOut,
    ActivityRuleConfigUpdate,
    PreviewResponse,
    PreviewSegmentOut,
)

router = APIRouter(
    prefix="/api/v1/settings/rule-configs",
    tags=["settings", "rule-configs"],
    dependencies=[Depends(verify_api_key)],
)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@router.get("/", response_model=list[ActivityRuleConfigOut])
def list_rule_configs(db: Session = Depends(get_db)) -> list[ActivityRuleConfigOut]:
    rows = (
        db.query(ActivityRuleConfig)
        .order_by(ActivityRuleConfig.activity_type_slug)
        .all()
    )
    return [ActivityRuleConfigOut.model_validate(r) for r in rows]


@router.get("/{slug}", response_model=ActivityRuleConfigOut)
def get_rule_config_endpoint(slug: str, db: Session = Depends(get_db)) -> ActivityRuleConfigOut:
    row = (
        db.query(ActivityRuleConfig)
        .filter(ActivityRuleConfig.activity_type_slug == slug)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule config not found")
    return ActivityRuleConfigOut.model_validate(row)


@router.patch("/{slug}", response_model=ActivityRuleConfigOut)
def patch_rule_config(
    slug: str,
    body: ActivityRuleConfigUpdate,
    db: Session = Depends(get_db),
) -> ActivityRuleConfigOut:
    row = (
        db.query(ActivityRuleConfig)
        .filter(ActivityRuleConfig.activity_type_slug == slug)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule config not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(row, field, value)

    db.commit()
    db.refresh(row)
    invalidate_rule_config_cache()
    return ActivityRuleConfigOut.model_validate(row)


@router.get("/{slug}/preview", response_model=PreviewResponse)
def preview_rule_config(
    slug: str,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PreviewResponse:
    row = (
        db.query(ActivityRuleConfig)
        .filter(ActivityRuleConfig.activity_type_slug == slug)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule config not found")

    if from_ is None or to is None:
        default_from, default_to = default_preview_range()
        from_ = from_ if from_ is not None else default_from
        to = to if to is not None else default_to
    from_ = _ensure_utc(from_)
    to = _ensure_utc(to)

    rows = (
        db.query(ActivitySegment)
        .filter(
            ActivitySegment.activity_type_slug == slug,
            ActivitySegment.started_at < to,
            or_(
                ActivitySegment.ended_at.is_(None),
                ActivitySegment.ended_at > from_,
            ),
        )
        .order_by(ActivitySegment.started_at)
        .all()
    )

    total_minutes = 0.0
    samples: list[PreviewSegmentOut] = []
    for seg in rows:
        end = seg.ended_at if seg.ended_at is not None else to
        clip_start = max(_ensure_utc(seg.started_at), from_)
        clip_end = min(_ensure_utc(end), to)
        if clip_end <= clip_start:
            continue
        duration_min = (clip_end - clip_start).total_seconds() / 60.0
        total_minutes += duration_min
        if len(samples) < 5:
            samples.append(
                PreviewSegmentOut(
                    id=seg.id,
                    started_at=seg.started_at,
                    ended_at=end,
                    duration_minutes=round(duration_min, 1),
                    source=seg.source,
                )
            )

    return PreviewResponse(
        segment_count=len(rows),
        total_minutes=round(total_minutes, 1),
        sample_segments=samples,
    )


def default_preview_range() -> tuple[datetime, datetime]:
    to = datetime.now(timezone.utc)
    from_ = to - timedelta(days=7)
    return from_, to
