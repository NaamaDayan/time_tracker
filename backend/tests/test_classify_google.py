from app.pipeline.classify import classify_google_calendar_event


def test_classify_work_from_meeting_keyword():
    slug, _ = classify_google_calendar_event({"summary": "Weekly sync with team"})
    assert slug == "work"


def test_classify_all_day_flag():
    _, meta = classify_google_calendar_event(
        {
            "summary": "Off",
            "start": {"date": "2026-05-01"},
            "end": {"date": "2026-05-02"},
        }
    )
    assert meta["is_all_day"] is True


def test_classify_timed_event_not_all_day():
    _, meta = classify_google_calendar_event(
        {
            "summary": "Standup",
            "start": {"dateTime": "2026-05-01T09:00:00Z"},
            "end": {"dateTime": "2026-05-01T09:30:00Z"},
        }
    )
    assert meta.get("is_all_day") is False
