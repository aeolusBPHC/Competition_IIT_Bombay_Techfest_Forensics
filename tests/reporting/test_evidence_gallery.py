import json
import hashlib

from reporting.evidence_gallery import build_evidence_gallery, find_media_report


def test_gallery_links_video_frames_metadata_and_anomalies(tmp_path):
    media_dir = tmp_path / "evidence"
    media_dir.mkdir()
    (media_dir / "flight.mov").write_bytes(b"video evidence")
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    report_path = report_dir / "case.html"
    media_report = {
        "generated_utc": "2026-11-24T00:00:00Z",
        "input": {"path": str(media_dir)},
        "items": [{
            "path": "flight.mov",
            "kind": "video",
            "format": "QuickTime",
            "mime": "video/quicktime",
            "size_bytes": 14,
            "sha256": "abc123",
            "origin": "directory",
            "analysis_method": "ffprobe and ExifTool",
            "metadata": {"fields": {"title": {"value": "<sample>", "source": "test"}}},
            "anomalies": [{"type": "TIMESTAMP_GAP", "severity": "warning",
                            "confidence": "medium", "gap_s": 4}],
            "frame_timeline": {"frames": [{"frame_number": 30, "offset_s": 1.0,
                                             "thumbnail_data_uri": "data:image/jpeg;base64,dGVzdA=="}]},
            "embedded_telemetry": {"status": "ok", "formats": ["GoPro_GPMF"],
                                   "sample_count": 1,
                                   "gpmf": {"decoded_sensor_sample_count": 21229}},
        }],
    }

    html = build_evidence_gallery(media_report, report_path)

    assert "<video" in html
    assert "../evidence/flight.mov" in html
    assert "Frame 30" in html
    assert "1 review finding(s)" in html
    assert "confidence medium" in html
    assert "Source: flight.mov" in html
    assert "ffprobe and ExifTool" in html
    assert "frame-thumb" in html
    assert "21,229 sensor sample(s)" in html
    assert "&lt;sample&gt;" in html
    assert "SHA-256 abc123" in html


def test_portable_gallery_copies_and_hash_verifies_source(tmp_path):
    media = tmp_path / "source" / "photo.jpg"
    media.parent.mkdir()
    content = b"image-source"
    media.write_bytes(content)
    report = tmp_path / "media_report.json"
    output = tmp_path / "reports" / "case.html"
    digest = hashlib.sha256(content).hexdigest()
    html = build_evidence_gallery({
        "input": {"path": str(media.parent)},
        "items": [{"path": "photo.jpg", "kind": "image", "sha256": digest,
                   "format": "JPEG", "size_bytes": len(content)}],
    }, output, portable_media=True)

    copied = output.parent / "case_assets" / f"{digest}_photo.jpg"
    assert copied.read_bytes() == content
    assert "Verified copies of source media" in html
    assert "case_assets" in html


def test_find_media_report_skips_invalid_json(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    valid = tmp_path / "media_report.json"
    valid.write_text(json.dumps({"items": []}), encoding="utf-8")

    report, path = find_media_report([invalid, valid])

    assert report == {"items": []}
    assert path == valid.resolve()

