import json
from pathlib import Path

import pytest

from app.connectors.activitywatch.schemas import ActivityWatchIngestBatch
from app.connectors.activitywatch.sync import SOURCE, sync_activitywatch_from_batch
from app.models import ActivitySegment, ActivityWindow, RawEvent, SourceAccount
from app.models.activity import ActivityType


@pytest.fixture
def aw_activity_types(db_session):
    for slug, label, color in [
        ("communication", "Communication", "#0ea5e9"),
        ("music_podcast", "Music / Podcast", "#84cc16"),
        ("phone_usage", "Phone Usage", "#64748b"),
    ]:
        if not db_session.query(ActivityType).filter(ActivityType.slug == slug).first():
            db_session.add(ActivityType(slug=slug, label=label, color=color))
    db_session.commit()


@pytest.fixture
def ingest_batch():
    path = Path(__file__).parent / "fixtures" / "activitywatch_ingest.json"
    data = json.loads(path.read_text())
    return ActivityWatchIngestBatch.model_validate(data)


def test_activitywatch_ingest_creates_raw_segments_and_windows(
    db_session, aw_activity_types, ingest_batch
):
    result = sync_activitywatch_from_batch(db_session, ingest_batch)

    assert result["raw_upserted"] == 3
    assert result["segments_written"] == 3

    account = db_session.query(SourceAccount).filter(SourceAccount.source == SOURCE).one()
    assert account.config_json["device_id"] == "test-aw-device"

    raw = db_session.query(RawEvent).filter(RawEvent.source == SOURCE).all()
    assert len(raw) == 3

    segments = db_session.query(ActivitySegment).filter(ActivitySegment.source == SOURCE).all()
    assert len(segments) == 3

    slugs = {s.activity_type_slug for s in segments}
    assert slugs == {"communication", "music_podcast", "phone_usage"}

    windows = db_session.query(ActivityWindow).all()
    assert len(windows) >= 3


def test_activitywatch_ingest_idempotent(db_session, aw_activity_types, ingest_batch):
    sync_activitywatch_from_batch(db_session, ingest_batch)
    sync_activitywatch_from_batch(db_session, ingest_batch)

    raw_count = db_session.query(RawEvent).filter(RawEvent.source == SOURCE).count()
    assert raw_count == 3
