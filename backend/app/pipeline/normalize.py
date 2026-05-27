from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import ActivitySegment, RawEvent
from app.pipeline.classify import classify_raw_event_safe
from app.pipeline.windows.service import recompute_windows_for_segments


def rebuild_segments_for_raw_events(db: Session, raw_event_ids: list[int]) -> int:
    if not raw_event_ids:
        return 0

    db.execute(delete(ActivitySegment).where(ActivitySegment.raw_event_id.in_(raw_event_ids)))

    events = db.query(RawEvent).filter(RawEvent.id.in_(raw_event_ids)).all()
    written = 0
    segment_ids: list[int] = []
    for event in events:
        classified = classify_raw_event_safe(
            event.source,
            event.payload,
            db=db,
            started_at=event.started_at,
            ended_at=event.ended_at,
        )
        if classified is None:
            continue
        activity_slug, metadata = classified
        segment = ActivitySegment(
            started_at=event.started_at,
            ended_at=event.ended_at,
            activity_type_slug=activity_slug,
            source=event.source,
            confidence=1.0,
            metadata_=metadata,
            raw_event_id=event.id,
        )
        db.add(segment)
        db.flush()
        segment_ids.append(segment.id)
        written += 1
    db.commit()

    if segment_ids:
        recompute_windows_for_segments(db, segment_ids)

    return written
