import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.connectors.samsung_health.schemas import SamsungHealthIngestBatch
from app.connectors.samsung_health.sync import SOURCE, sync_samsung_health_from_batch
from app.models import ActivitySegment, ActivityWindow, ActivityWindowSegment, RawEvent, SourceAccount
from app.models.activity import ActivityType


@pytest.fixture
def health_activity_types(db_session):
    for slug, label, color in [
        ("sleep", "Sleep", "#6366f1"),
        ("sport", "Sport", "#22c55e"),
    ]:
        if not db_session.query(ActivityType).filter(ActivityType.slug == slug).first():
            db_session.add(ActivityType(slug=slug, label=label, color=color))
    db_session.commit()


@pytest.fixture
def ingest_batch():
    path = Path(__file__).parent / "fixtures" / "samsung_health_ingest.json"
    data = json.loads(path.read_text())
    return SamsungHealthIngestBatch.model_validate(data)


def test_samsung_ingest_creates_raw_segments_and_windows(db_session, health_activity_types, ingest_batch):
    result = sync_samsung_health_from_batch(db_session, ingest_batch)

    assert result["raw_upserted"] == 3
    assert result["segments_written"] == 3

    account = db_session.query(SourceAccount).filter(SourceAccount.source == SOURCE).one()
    assert account.config_json["device_id"] == "test-device-1"

    raw = db_session.query(RawEvent).filter(RawEvent.source == SOURCE).all()
    assert len(raw) == 3

    segments = db_session.query(ActivitySegment).filter(ActivitySegment.source == SOURCE).all()
    assert len(segments) == 3

    sleep_seg = next(s for s in segments if s.metadata_.get("health_category") == "sleep")
    assert sleep_seg.activity_type_slug == "sleep"

    walk_seg = next(s for s in segments if s.metadata_.get("health_category") == "walk")
    assert walk_seg.metadata_["exclude_from_windows"] is True

    windows = db_session.query(ActivityWindow).all()
    window_seg_ids = {
        link.segment_id
        for link in db_session.query(ActivityWindowSegment).all()
    }
    assert walk_seg.id not in window_seg_ids
    assert len(windows) >= 2


def test_samsung_ingest_idempotent(db_session, health_activity_types, ingest_batch):
    sync_samsung_health_from_batch(db_session, ingest_batch)
    sync_samsung_health_from_batch(db_session, ingest_batch)

    raw_count = db_session.query(RawEvent).filter(RawEvent.source == SOURCE).count()
    assert raw_count == 3
