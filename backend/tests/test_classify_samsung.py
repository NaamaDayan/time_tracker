from app.pipeline.classify import (
    classify_raw_event,
    classify_samsung_health_record,
)


def test_classify_sleep_session():
    activity, meta = classify_samsung_health_record(
        {
            "record_type": "sleep_session",
            "ended_at": "2026-05-17T06:15:00Z",
            "duration_min": 465,
        }
    )
    assert activity == "sleep"
    assert meta["health_category"] == "sleep"
    assert meta["calendar_visible"] is True
    assert meta["exclude_from_windows"] is False
    assert meta["woke_at"] == "2026-05-17T06:15:00Z"
    assert meta["duration_min"] == 465


def test_classify_exercise_session():
    activity, meta = classify_samsung_health_record(
        {
            "record_type": "exercise_session",
            "exercise_type": "RUNNING",
            "calories": 320,
            "duration_sec": 2700,
        }
    )
    assert activity == "sport"
    assert meta["health_category"] == "exercise"
    assert meta["exercise_type"] == "RUNNING"
    assert meta["calories"] == 320


def test_classify_daily_steps():
    activity, meta = classify_samsung_health_record(
        {
            "record_type": "daily_steps",
            "local_date": "2026-05-16",
            "step_count": 8420,
        }
    )
    assert activity == "sport"
    assert meta["health_category"] == "walk"
    assert meta["exclude_from_windows"] is True
    assert meta["step_count"] == 8420


def test_classify_raw_event_dispatcher():
    activity, _ = classify_raw_event(
        "samsung_health",
        {"record_type": "sleep_session", "ended_at": "2026-05-17T06:00:00Z"},
    )
    assert activity == "sleep"
