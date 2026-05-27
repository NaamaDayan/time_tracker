from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import ActivityRuleConfig, ActivitySegment, RawEvent
from app.pipeline.classify import classify_raw_event_safe
from app.pipeline.rule_config import (
    get_merge_gap_minutes,
    get_rule_config,
    invalidate_rule_config_cache,
)
from app.pipeline.windows.recompute import recompute_type_in_range
from app.seed_rule_configs import DEFAULT_RULE_CONFIGS, seed_rule_configs


@pytest.fixture
def api_client(db_session):
  from app.database import get_db

  def override_get_db():
    yield db_session

  app.dependency_overrides[get_db] = override_get_db
  client = TestClient(app)
  yield client
  app.dependency_overrides.clear()


def test_seed_rule_configs_inserts_14_rows(db_session):
    invalidate_rule_config_cache()
    count = db_session.query(ActivityRuleConfig).count()
    assert count == 14


def test_get_rule_config_cached(db_session):
    invalidate_rule_config_cache()
    cfg1 = get_rule_config("work", db_session)
    cfg2 = get_rule_config("work", db_session)
    assert cfg1.min_duration_minutes == 20
    assert cfg1 is cfg2


def test_enabled_false_skips_classification(db_session):
    invalidate_rule_config_cache()
    work = db_session.query(ActivityRuleConfig).filter_by(activity_type_slug="work").one()
    work.enabled = False
    db_session.commit()
    invalidate_rule_config_cache()

    started = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    ended = started + timedelta(minutes=30)
    result = classify_raw_event_safe(
        "activitywatch_desktop",
        {"app": "Code", "title": "main.py"},
        db=db_session,
        started_at=started,
        ended_at=ended,
    )
    assert result is None


def test_min_duration_filters_short_segments(db_session):
    invalidate_rule_config_cache()
    work = db_session.query(ActivityRuleConfig).filter_by(activity_type_slug="work").one()
    work.min_duration_minutes = 30
    db_session.commit()
    invalidate_rule_config_cache()

    started = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    ended = started + timedelta(minutes=10)
    result = classify_raw_event_safe(
        "activitywatch_desktop",
        {"app": "Code", "title": "main.py"},
        db=db_session,
        started_at=started,
        ended_at=ended,
    )
    assert result is None


def test_work_days_exclude_friday(db_session):
    invalidate_rule_config_cache()
    work = db_session.query(ActivityRuleConfig).filter_by(activity_type_slug="work").one()
    work.custom_params = {
        "work_days": [0, 1, 2, 3, 6],
        "work_hours_start": 8,
        "work_hours_end": 20,
    }
    db_session.commit()
    invalidate_rule_config_cache()

    friday = datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc)
    ended = friday + timedelta(minutes=45)
    result = classify_raw_event_safe(
        "activitywatch_desktop",
        {"app": "Code", "title": "main.py"},
        db=db_session,
        started_at=friday,
        ended_at=ended,
    )
    assert result is None

    monday = datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc)
    ended_mon = monday + timedelta(minutes=45)
    result_mon = classify_raw_event_safe(
        "activitywatch_desktop",
        {"app": "Code", "title": "main.py"},
        db=db_session,
        started_at=monday,
        ended_at=ended_mon,
    )
    assert result_mon is not None
    assert result_mon[0] == "work"


def test_merge_gap_from_rule_config(db_session):
    invalidate_rule_config_cache()
    sport = db_session.query(ActivityRuleConfig).filter_by(activity_type_slug="sport").one()
    sport.merge_gap_minutes = 99
    db_session.commit()
    invalidate_rule_config_cache()
    assert get_merge_gap_minutes("sport", db_session) == 99


def test_patch_min_duration_used_on_next_classify(db_session, api_client):
    invalidate_rule_config_cache()
    response = api_client.patch(
        "/api/v1/settings/rule-configs/sport",
        json={"min_duration_minutes": 60},
        headers={"X-API-Key": "dev-only-change-me"},
    )
    assert response.status_code == 200
    invalidate_rule_config_cache()

    started = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    ended = started + timedelta(minutes=30)
    with patch("app.pipeline.classify.classify_geofence_event") as mock_geo:
        mock_geo.return_value = ("sport", {"zone_name": "gym"})
        result = classify_raw_event_safe(
            "geofence",
            {"zone_name": "gym", "transition": "ENTER"},
            db=db_session,
            started_at=started,
            ended_at=ended,
        )
    assert result is None


def test_list_rule_configs_api(api_client):
    response = api_client.get(
        "/api/v1/settings/rule-configs/",
        headers={"X-API-Key": "dev-only-change-me"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 14
    slugs = {row["activity_type_slug"] for row in data}
    assert slugs == {row["activity_type_slug"] for row in DEFAULT_RULE_CONFIGS}


def test_preview_endpoint(db_session, api_client):
    started = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
    ended = started + timedelta(minutes=30)
    seg = ActivitySegment(
        started_at=started,
        ended_at=ended,
        activity_type_slug="work",
        source="activitywatch_desktop",
        confidence=1.0,
    )
    db_session.add(seg)
    db_session.commit()

    from_ = "2026-05-01T00:00:00Z"
    to = "2026-05-02T00:00:00Z"
    response = api_client.get(
        f"/api/v1/settings/rule-configs/work/preview?from={from_}&to={to}",
        headers={"X-API-Key": "dev-only-change-me"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["segment_count"] == 1
    assert body["total_minutes"] == 30.0
    assert len(body["sample_segments"]) == 1


def test_recompute_uses_per_type_merge_gap(db_session):
    invalidate_rule_config_cache()
    sport_cfg = db_session.query(ActivityRuleConfig).filter_by(activity_type_slug="sport").one()
    sport_cfg.merge_gap_minutes = 120
    db_session.commit()
    invalidate_rule_config_cache()

    t0 = datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=20)
    t2 = t1 + timedelta(minutes=30)
    t3 = t2 + timedelta(minutes=20)
    for start, end in [(t0, t1), (t2, t3)]:
        db_session.add(
            ActivitySegment(
                started_at=start,
                ended_at=end,
                activity_type_slug="sport",
                source="test",
                confidence=1.0,
            )
        )
    db_session.commit()

    written = recompute_type_in_range(
        db_session,
        activity_type_slug="sport",
        from_=t0 - timedelta(hours=1),
        to=t3 + timedelta(hours=1),
    )
    assert written == 1
