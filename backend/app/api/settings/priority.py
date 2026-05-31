from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import verify_api_key
from app.database import get_db
from app.models import ActivityType, ActivityTypePriority
from app.pipeline.activity_priority import invalidate_activity_priority_cache
from app.schemas.activity_type_priority import ActivityPriorityOut, ActivityPriorityPutItem

router = APIRouter(
    prefix="/api/v1/settings/activity-priority",
    tags=["settings", "activity-priority"],
    dependencies=[Depends(verify_api_key)],
)

EMOJI_BY_SLUG: dict[str, str] = {
    "sleep": "😴",
    "sport": "🏋️",
    "work": "💻",
    "family": "👨‍👩‍👧",
    "fun": "🎉",
    "meal_prep": "🍳",
    "watching_tv": "📺",
    "bedroom": "🛏️",
    "bathroom": "🚿",
    "consuming": "📱",
    "communication": "💬",
    "music": "🎵",
    "podcasts": "🎧",
    "transport": "🚗",
}


@router.get("/", response_model=list[ActivityPriorityOut])
def list_activity_priority(db: Session = Depends(get_db)) -> list[ActivityPriorityOut]:
    rows = (
        db.query(ActivityTypePriority, ActivityType)
        .join(ActivityType, ActivityTypePriority.activity_type_slug == ActivityType.slug)
        .order_by(ActivityTypePriority.rank.asc())
        .all()
    )
    return [
        ActivityPriorityOut(
            slug=priority.activity_type_slug,
            rank=priority.rank,
            display_name=atype.label,
            emoji=EMOJI_BY_SLUG.get(priority.activity_type_slug, "•"),
            color=atype.color,
        )
        for priority, atype in rows
    ]


@router.put("/", response_model=list[ActivityPriorityOut])
def replace_activity_priority(
    body: list[ActivityPriorityPutItem],
    db: Session = Depends(get_db),
) -> list[ActivityPriorityOut]:
    existing_slugs = {
        row.activity_type_slug
        for row in db.query(ActivityTypePriority.activity_type_slug).all()
    }
    if not existing_slugs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Priority table is empty; restart the API to seed defaults",
        )

    body_slugs = {item.slug for item in body}
    ranks = [item.rank for item in body]

    if len(ranks) != len(set(ranks)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate ranks not allowed",
        )

    unknown = sorted(body_slugs - existing_slugs)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown activity types: {', '.join(unknown)}",
        )

    missing = sorted(existing_slugs - body_slugs)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing activity types: {', '.join(missing)}",
        )

    valid_type_slugs = {
        row.slug for row in db.query(ActivityType.slug).filter(ActivityType.slug.in_(body_slugs)).all()
    }
    invalid_fk = sorted(body_slugs - valid_type_slugs)
    if invalid_fk:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown activity types: {', '.join(invalid_fk)}",
        )

    expected_ranks = set(range(1, len(existing_slugs) + 1))
    if set(ranks) != expected_ranks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ranks must be exactly 1 through {len(existing_slugs)}",
        )

    for item in body:
        row = (
            db.query(ActivityTypePriority)
            .filter(ActivityTypePriority.activity_type_slug == item.slug)
            .first()
        )
        if row:
            row.rank = item.rank

    db.commit()
    invalidate_activity_priority_cache()
    return list_activity_priority(db)
