from app.pipeline.classify import classify_activitywatch_event, classify_raw_event


def test_classify_whatsapp_communication():
    activity, meta = classify_activitywatch_event(
        {"record_type": "app_session", "app": "WhatsApp", "package": "com.whatsapp"}
    )
    assert activity == "communication"
    assert meta["app"] == "WhatsApp"
    assert meta["package"] == "com.whatsapp"


def test_classify_spotify_music_podcast():
    activity, _ = classify_activitywatch_event(
        {"package": "com.spotify.music", "data": {"app": "Spotify"}}
    )
    assert activity == "music_podcast"


def test_classify_youtube_consuming():
    activity, _ = classify_activitywatch_event(
        {"app": "YouTube", "package": "com.google.android.youtube"}
    )
    assert activity == "consuming"


def test_classify_lithium_read():
    activity, _ = classify_activitywatch_event({"package": "com.faultexception.lithium"})
    assert activity == "read"


def test_classify_maps_transport():
    activity, _ = classify_activitywatch_event(
        {"app": "Maps", "package": "com.google.android.apps.maps"}
    )
    assert activity == "transport"


def test_classify_slack_communication():
    activity, _ = classify_activitywatch_event({"app": "Slack"})
    assert activity == "communication"


def test_classify_unknown_phone_usage():
    activity, _ = classify_activitywatch_event(
        {"app": "Settings", "package": "com.android.settings"}
    )
    assert activity == "phone_usage"


def test_classify_raw_event_dispatcher():
    activity, _ = classify_raw_event(
        "activitywatch",
        {"app": "Telegram", "record_type": "app_session"},
    )
    assert activity == "communication"
