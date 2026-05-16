from app.pipeline.classify import classify_clockify_entry


def test_classify_defaults_to_work():
    activity, meta = classify_clockify_entry(
        {"id": "1", "description": "test", "project": {"name": "P"}, "tags": []}
    )
    assert activity == "work"
    assert meta["project"] == "P"
