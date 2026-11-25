from __future__ import annotations

import hashlib
import os
import struct

import pytest

from media import embedded_telemetry, gpmf


def _klv(key: str, kind: str, size: int, repeat: int, data: bytes) -> bytes:
    record = key.encode("ascii") + kind.encode("latin-1") + bytes([size]) + repeat.to_bytes(2, "big") + data
    return record + b"\0" * ((-len(record)) % 4)


def _container(key: str, contents: bytes) -> bytes:
    return _klv(key, "\0", 1, len(contents), contents)


def test_decodes_scaled_sensor_vectors_and_rejects_truncated_record():
    sensor = _klv("ACCL", "s", 6, 1, struct.pack(">hhh", 418, -209, 836))
    stream = _container("STRM",
                        _klv("SCAL", "l", 4, 3, struct.pack(">iii", 418, 418, 418)) + sensor)
    device = _container("DEVC", stream)

    result = gpmf.decode(device, track_index=2)

    assert result["decoded_sensor_sample_count"] == 1
    assert result["packets"][0]["streams"][0]["values"] == [[1.0, -0.5, 2.0]]
    assert result["packets"][0]["streams"][0]["axis_order"] == ["z", "x", "y"]
    with pytest.raises(gpmf.GPMFError, match="truncated"):
        gpmf.decode(b"DEVC", track_index=2)


def test_real_gopro_hero5_sample_when_provided():
    sample_path = os.environ.get("GPMF_SAMPLE")
    if not sample_path:
        pytest.skip("set GPMF_SAMPLE to the GoPro GPMF Hero5 sample to run integration coverage")
    expected_sha256 = "2e4008e4d66efc1413fbcdeb568b0af82da623435c017e696410a5a4f2d7659b"
    digest = hashlib.sha256()
    with open(sample_path, "rb") as sample:
        for block in iter(lambda: sample.read(1024 * 1024), b""):
            digest.update(block)
    assert digest.hexdigest() == expected_sha256

    result = embedded_telemetry.read(sample_path, timeout_s=180)

    assert result["status"] == "ok"
    assert "GoPro_GPMF" in result["formats"]
    assert result["gpmf"]["decoded_sensor_sample_count"] > 0
    streams = [stream["stream"] for packet in result["gpmf"]["packets"]
               for stream in packet["streams"]]
    assert "ACCL" in streams
    assert "GYRO" in streams
    assert "GPS5" in streams
