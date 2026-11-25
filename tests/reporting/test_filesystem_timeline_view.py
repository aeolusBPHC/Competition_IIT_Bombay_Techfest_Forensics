from reporting.filesystem_timeline_view import build_filesystem_timeline


def test_timeline_view_labels_deleted_entries_and_escapes_content():
    timeline = {
        "status": "ok",
        "summary": {"entry_count": 2, "allocated_entries": 1,
                    "deleted_entries": 1, "event_count": 1},
        "timestamp_notes": ["Filesystem timestamps are observations."],
        "events": [{
            "time_utc": "2024-01-01T00:00:00+00:00",
            "timestamp_type": "modified",
            "path": "/DCIM/<gone>.jpg",
            "entry_status": "deleted_entry",
            "meaning_and_limits": "mtime is not proof of deletion.",
        }],
    }

    rendered = build_filesystem_timeline(timeline)

    assert "Removable-media" not in rendered
    assert "2 entries" in rendered
    assert "deleted_entry" in rendered
    assert "filesystem-deleted" in rendered
    assert "/DCIM/&lt;gone&gt;.jpg" in rendered
    assert "Filesystem timestamps are observations." in rendered


def test_timeline_view_limits_large_tables():
    events = [
        {"time_utc": f"2024-01-01T00:00:{index:02d}+00:00",
         "timestamp_type": "modified", "path": f"/file-{index}",
         "entry_status": "allocated_entry", "meaning_and_limits": "mtime"}
        for index in range(3)
    ]
    rendered = build_filesystem_timeline({"events": events, "summary": {}}, display_limit=2)

    assert rendered.count("<tr>") == 3  # header and two displayed events
    assert "Showing the first 2 of 3 events" in rendered
