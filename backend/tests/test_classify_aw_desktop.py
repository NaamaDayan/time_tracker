from app.pipeline.classify import classify_activitywatch_desktop_event, classify_raw_event


def test_defaults_to_work():
    activity, meta = classify_activitywatch_desktop_event(
        {"app": "Visual Studio Code", "title": "main.py"}
    )
    assert activity == "work"
    assert meta["app"] == "Visual Studio Code"


def test_slack_is_communication():
    activity, _ = classify_activitywatch_desktop_event(
        {"app": "Slack", "title": "#general"}
    )
    assert activity == "communication"


def test_spotify_is_music():
    activity, _ = classify_activitywatch_desktop_event(
        {"app": "Spotify", "title": "Now Playing"}
    )
    assert activity == "music_podcast"


def test_youtube_is_consuming():
    activity, _ = classify_activitywatch_desktop_event(
        {"app": "Google Chrome", "title": "YouTube - Funny Video"}
    )
    assert activity == "consuming"


def test_kindle_is_read():
    activity, _ = classify_activitywatch_desktop_event(
        {"app": "Kindle", "title": "My Book"}
    )
    assert activity == "read"


def test_classify_raw_event_dispatches():
    activity, meta = classify_raw_event(
        "activitywatch_desktop",
        {"app": "Terminal", "title": "bash"},
    )
    assert activity == "work"
    assert meta["app"] == "Terminal"
