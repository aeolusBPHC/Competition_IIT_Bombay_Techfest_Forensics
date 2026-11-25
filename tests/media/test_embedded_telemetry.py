from __future__ import annotations

import json
import subprocess

from media import embedded_telemetry


def _run_stub(monkeypatch, streams, records, version="13.60"):
    def fake_run(command, timeout_s):
        if "-show_streams" in command:
            return subprocess.CompletedProcess(command, 0, json.dumps({"streams": streams}), "")
        if command[-1] == "-ver":
            return subprocess.CompletedProcess(command, 0, version, "")
        return subprocess.CompletedProcess(command, 0, json.dumps(records), "")

    monkeypatch.setattr(embedded_telemetry, "_run", fake_run)
    embedded_telemetry._exiftool_version.cache_clear()


def test_reads_gopro_gpmf_gps_altitude_and_camera_motion(monkeypatch):
    _run_stub(
        monkeypatch,
        [{"index": 2, "codec_type": "data", "codec_tag_string": "gpmd",
          "codec_name": "unknown", "tags": {"handler_name": "GoPro MET"}}],
        [{
            "Doc1:GoPro:GPSLatitude": 47.5,
            "Doc1:GoPro:GPSLongitude": 16.2,
            "Doc1:GoPro:GPSAltitude": 512.4,
            "Doc1:GoPro:GPSDateTime": "2024-02-03T04:05:06.000Z",
            "Doc1:GoPro:GPSFixType": 3,
            "Doc1:GoPro:GPSHDOP": 0.7,
            "Doc1:GoPro:GPSSpeed": 4.2,
            "Doc1:GoPro:ISO": 200,
            "Doc1:GoPro:ShutterSpeed": "1/100",
            "Doc1:GoPro:Accelerometer": [1.0, 2.0, 3.0],
            "Doc1:GoPro:Gyroscope": [0.1, 0.2, 0.3],
        }],
    )

    result = embedded_telemetry.read("gopro.mp4", ffprobe="ffprobe", exiftool="exiftool")

    assert result["status"] == "ok"
    assert result["formats"] == ["GoPro_GPMF"]
    sample = result["samples"][0]
    assert sample["gps"]["latitude"] == 47.5
    assert sample["gps"]["longitude"] == 16.2
    assert sample["gps"]["quality"]["fix_type"]["value"] == 3
    assert sample["gps"]["quality"]["hdop"]["value"] == 0.7
    assert sample["gps"]["coordinate_reference"].startswith("WGS84")
    assert sample["speed"]["value"] == 4.2
    assert sample["camera_settings"]["iso"]["value"] == 200
    assert sample["camera_settings"]["shutter_time"]["units"] is None
    assert sample["altitude"]["absolute_m"]["value"] == 512.4
    assert sample["timestamp"]["basis"] == "utc"
    assert sample["camera_motion"]["accelerometer"]["value"] == [1.0, 2.0, 3.0]
    assert sample["camera_motion"]["accelerometer"]["units"] == "m/s^2"
    assert sample["camera_motion"]["gyroscope"]["units"] == "rad/s"
    assert "Doc1:GoPro:GPSLatitude" in sample["raw_tags"]


def test_reads_dji_djmd_and_preserves_unknown_time_and_units(monkeypatch):
    _run_stub(
        monkeypatch,
        [{"index": 3, "codec_type": "data", "codec_tag_string": "djmd",
          "codec_name": "unknown", "tags": {"handler_name": "DJI meta"}}],
        [{
            "Doc1:DJI:dvtm_wm265e_3-3-4-1:GPSLatitude": 47.6,
            "Doc1:DJI:dvtm_wm265e_3-3-4-1:GPSLongitude": 16.3,
            "Doc1:DJI:dvtm_wm265e_3-3-4-2:AbsoluteAltitude": 502.0,
            "Doc1:DJI:dvtm_wm265e_3-3-5-1:RelativeAltitude": 48.0,
            "Doc1:DJI:dvtm_wm265e_3-3-3:DroneYaw": 90.0,
            "Doc1:DJI:dvtm_wm265e_3-1-2:TimeStamp": 1710000000,
        }],
    )

    result = embedded_telemetry.read("dji.mp4", ffprobe="ffprobe", exiftool="exiftool")

    assert result["status"] == "ok"
    assert result["formats"] == ["DJI_djmd"]
    sample = result["samples"][0]
    assert sample["gps"]["latitude"] == 47.6
    assert sample["altitude"]["absolute_m"]["value"] == 502.0
    assert sample["altitude"]["relative_m"]["value"] == 48.0
    assert sample["altitude"]["relative_m"]["units"] is None
    assert "unknown" in sample["altitude"]["relative_m"]["reference"]
    assert sample["camera_motion"]["aircraft"]["roll_pitch_yaw"] == [None, None, 90.0]
    assert sample["camera_motion"]["aircraft"]["units"] is None
    assert sample["timestamp"]["basis"] == "source_clock_uninterpreted"
    assert sample["timestamp"]["value"] == 1710000000


def test_reports_current_exiftool_limit_for_dji_track(monkeypatch):
    _run_stub(
        monkeypatch,
        [{"index": 1, "codec_type": "data", "codec_tag_string": "djmd"}],
        [], version="12.40",
    )

    result = embedded_telemetry.read("dji.mp4", ffprobe="ffprobe", exiftool="exiftool")

    assert result["status"] == "no_samples_decoded"
    assert any("requires ExifTool 13.05 or newer" in warning for warning in result["warnings"])


def test_reports_no_embedded_telemetry_track(monkeypatch):
    _run_stub(monkeypatch, [{"index": 0, "codec_type": "video", "codec_tag_string": "avc1"}], [])

    result = embedded_telemetry.read("ordinary.mp4", ffprobe="ffprobe", exiftool="exiftool")

    assert result["status"] == "no_embedded_telemetry_track"
    assert result["formats"] == []
