from types import SimpleNamespace

from media import filesystem_timeline
from media.extractor import MediaExtractor


def test_parse_bodyfile_labels_timestamps_and_deleted_entry():
    body = "\n".join([
        "0|/DCIM/IMG_0001.JPG|12-128-1|r/rrwxrwxrwx|0|0|100|1700000001|1700000002|1700000003|1700000004",
        "0|/DCIM/DELETED.JPG (deleted-realloc)|13-128-1|r/rrwxrwxrwx|0|0|200|1700000011|1700000012|1700000013|0",
    ])

    records = filesystem_timeline.parse_bodyfile(body, 2048)
    events = filesystem_timeline.build_events(records)

    assert records[0]["status"] == "allocated_entry"
    assert records[0]["timestamps"]["filesystem_created"]["source_field"] == "crtime"
    assert "not a creation time" in records[0]["timestamps"]["metadata_changed"]["meaning_and_limits"]
    assert records[1]["path"] == "/DCIM/DELETED.JPG"
    assert records[1]["raw_name"].endswith("(deleted-realloc)")
    assert records[1]["status"] == "deleted_entry_reallocated"
    assert records[1]["deletion_time"] is None
    assert "does not provide" in records[1]["deletion_note"]
    assert records[1]["timestamps"]["filesystem_created"] is None
    assert filesystem_timeline.filesystem_timestamp_limits("FAT32")[0].startswith("FAT timestamps")
    assert filesystem_timeline.filesystem_timestamp_limits("NTFS")[0].startswith("NTFS stores")
    assert events == sorted(events, key=lambda event: event["time_epoch_s"])
    assert all(event["partition_offset_sectors"] == 2048 for event in events)


def test_extract_uses_fls_for_each_partition_and_summarizes(monkeypatch):
    body = "0|/image.jpg|12-128-1|r/rrwxrwxrwx|0|0|100|1700000001|1700000002|1700000003|1700000004"
    calls = []
    monkeypatch.setattr(filesystem_timeline.shutil, "which",
                        lambda name: f"/usr/bin/{name}" if name in {"fls", "fsstat"} else None)

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[0].endswith("fsstat"):
            return SimpleNamespace(returncode=0, stdout="File System Type: NTFS\n", stderr="")
        return SimpleNamespace(returncode=0, stdout=body, stderr="")

    monkeypatch.setattr(filesystem_timeline.subprocess, "run", fake_run)
    result = filesystem_timeline.extract("card.img", [0, 4096])

    assert result["status"] == "ok"
    assert result["summary"] == {
        "partition_count": 2,
        "entry_count": 2,
        "allocated_entries": 2,
        "deleted_entries": 0,
        "event_count": 8,
    }
    fls_calls = [command for command in calls if command[0].endswith("fls")]
    assert len(fls_calls) == 2
    assert result["partitions"][0]["filesystem_type"] == "NTFS"
    assert any("NTFS stores" in note for note in result["timestamp_notes"])
    assert fls_calls[0][-2:] == ["0", "card.img"]


def test_disk_image_media_report_includes_filesystem_timeline(tmp_path, monkeypatch):
    image = tmp_path / "card.img"
    boot_sector = bytearray(512)
    boot_sector[510:512] = b"\x55\xaa"
    image.write_bytes(boot_sector)
    timeline = {"status": "ok", "records": [], "events": [], "summary": {}}
    monkeypatch.setattr(MediaExtractor, "_partition_offsets", lambda self, path: [0])
    monkeypatch.setattr(MediaExtractor, "_recover_from_image", lambda self, path, work, offsets: [])
    monkeypatch.setattr(filesystem_timeline, "extract", lambda path, offsets: timeline)

    report = MediaExtractor(image).extract()

    assert report["filesystem_timeline"] == timeline
    assert report["input"]["type"] == "disk_image"
