from __future__ import annotations

import json
import re
import subprocess

import pytest

from media import frame_timeline


def _probe_output(frames):
    return json.dumps({
        "streams": [{"index": 0, "codec_name": "h264", "width": 1920,
                     "height": 1080, "avg_frame_rate": "30/1"}],
        "frames": frames,
    })


def _frame(pts, **extra):
    return {"best_effort_timestamp_time": str(pts), "pkt_duration_time": "0.033333",
            "key_frame": 0, "pict_type": "P", "width": 1920, "height": 1080,
            **extra}


def _fake_tools(monkeypatch, frames):
    monkeypatch.setattr(frame_timeline.shutil, "which",
                        lambda name: f"/usr/bin/{name}" if name in {"ffprobe", "ffmpeg"} else None)

    def fake_run(command, **kwargs):
        if command[0].endswith("ffmpeg"):
            selected = re.findall(r"eq\(n\\,(\d+)\)", command[7])
            return subprocess.CompletedProcess(command[0], 0,
                                                b"".join(b"\xff\xd8preview\xff\xd9" for _ in selected), b"")
        return subprocess.CompletedProcess(command[0], 0, _probe_output(frames), "")

    monkeypatch.setattr(frame_timeline.subprocess, "run", fake_run)


def test_build_samples_frames_on_media_clock_from_first_pts(monkeypatch):
    frames = [_frame(-0.08, key_frame=1), _frame(0), _frame(0.25),
              _frame(1.05), _frame(1.98), _frame(2.10)]
    _fake_tools(monkeypatch, frames)

    result = frame_timeline.build("evidence.mp4", interval_s=1.0,
                                  source_path="evidence.mp4", source_sha256="abc")

    assert result["status"] == "ok"
    assert result["frame_count_decoded"] == 6
    assert result["frame_count_indexed"] == 3
    assert [f["frame_number"] for f in result["frames"]] == [0, 3, 4]
    assert [f["pts_s"] for f in result["frames"]] == [-0.08, 1.05, 1.98]
    assert [f["offset_s"] for f in result["frames"]] == pytest.approx([0, 1.13, 2.06])
    assert result["frames"][0]["timestamp_source"] == "best_effort_timestamp_time"
    assert result["frames"][0]["key_frame"] is True
    assert result["stream"]["codec_name"] == "h264"
    assert result["source_sha256"] == "abc"
    assert result["frames"][0]["thumbnail_data_uri"].startswith("data:image/jpeg;base64,")


def test_build_can_index_every_frame_and_skip_untimed_frames(monkeypatch):
    frames = [_frame(5.0), {"pkt_dts_time": "5.03"}, _frame(5.1)]
    _fake_tools(monkeypatch, frames)

    result = frame_timeline.build("evidence.mp4", interval_s=None)

    assert [f["frame_number"] for f in result["frames"]] == [0, 2]
    assert result["frame_count_timed"] == 2
    assert result["warnings"] == ["1 decoded frames had no usable presentation timestamp"]


def test_build_retains_non_monotonic_pts_even_when_sampled_frame_is_skipped(monkeypatch):
    frames = [_frame(0.0), _frame(1.0), _frame(0.5), _frame(2.0)]
    _fake_tools(monkeypatch, frames)

    result = frame_timeline.build("evidence.mp4", interval_s=1.0)

    assert result["frame_count_indexed"] == 3
    assert result["timestamp_order_findings"][0]["type"] == "NON_MONOTONIC_TIMESTAMP"
    assert result["timestamp_order_findings"][0]["frame_number"] == 2


def test_build_reports_missing_ffprobe(monkeypatch):
    monkeypatch.setattr(frame_timeline.shutil, "which", lambda _: None)

    result = frame_timeline.build("evidence.mp4")

    assert result["status"] == "unavailable"
    assert result["frames"] == []
    assert "ffprobe is not installed" in result["warnings"][0]


def test_build_reports_probe_failure_without_raising(monkeypatch):
    monkeypatch.setattr(frame_timeline.shutil, "which",
                        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None)
    monkeypatch.setattr(frame_timeline.subprocess, "run", lambda *a, **kw:
                        subprocess.CompletedProcess(a[0], 1, "", "invalid input"))

    result = frame_timeline.build("evidence.mp4")

    assert result["status"] == "error"
    assert result["frames"] == []
    assert "invalid input" in result["warnings"][0]


def test_build_rejects_non_positive_sampling_interval():
    with pytest.raises(ValueError, match="interval_s must be positive"):
        frame_timeline.build("evidence.mp4", interval_s=0)
    with pytest.raises(ValueError, match="interval_s must be positive"):
        frame_timeline.build("evidence.mp4", interval_s=float("nan"))
