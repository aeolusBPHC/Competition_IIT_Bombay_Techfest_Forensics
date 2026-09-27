"""Tests for the EmuFlight Blackbox decoder and parser."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from platform_parsers.emuflight.blackbox_decoder import decode_bytes
from platform_parsers.emuflight.blackbox_parser import (
    EmuFlightBlackboxParser,
    EmuFlightUnitConfig,
)
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))
from create_emuflight_fixture import HOME, build_fixture, build_log  # noqa: E402


@pytest.fixture(scope="module")
def fixture_file(tmp_path_factory):
    data, truths, log0_len = build_fixture()
    path = tmp_path_factory.mktemp("emu") / "synthetic_emuflight.bbl"
    path.write_bytes(data)
    return path, data, truths, log0_len


# ------------------------------------------------------------ identification
def test_identify_emuflight(fixture_file):
    path, *_ = fixture_file
    result = EmuFlightBlackboxParser.identify(path)
    assert result["supported"] is True
    assert result["platform"] == "EmuFlight"
    assert result["format"] == "Blackbox"
    assert result["confidence"] == "HIGH"
    assert "EmuFlight" in result["indicators"]["firmware_revision"]


def test_identify_rejects_betaflight_blackbox(tmp_path):
    data, _ = build_log("Betaflight 4.4.2 (abcdef) STM32F405", 5, 1_000_000, 1, False)
    path = tmp_path / "bf.bbl"
    path.write_bytes(data)
    assert EmuFlightBlackboxParser.identify(path)["supported"] is False


def test_identify_rejects_non_blackbox(tmp_path):
    path = tmp_path / "x.ulg"
    path.write_bytes(b"ULog\x01\x12\x35" + b"\x00" * 100)
    assert EmuFlightBlackboxParser.identify(path)["supported"] is False


# ------------------------------------------------------------------ decoding
def test_every_main_frame_value_matches_ground_truth(fixture_file):
    _, data, truths, _ = fixture_file
    logs = decode_bytes(data)
    assert len(logs) == 2
    for log, truth in zip(logs, truths):
        assert len(log.main_frames) == len(truth["main"])
        for decoded, expected in zip(log.main_frames, truth["main"]):
            for name, value in expected.items():
                assert decoded[name] == value, (name, decoded["loopIteration"])


def test_gps_frames_and_home_prediction(fixture_file):
    _, data, truths, _ = fixture_file
    log = decode_bytes(data)[0]
    assert log.stats.gps_frames_without_home == 1  # frame logged before home
    assert len(log.gps_frames) == len(truths[0]["gps"])
    for decoded, expected in zip(log.gps_frames, truths[0]["gps"]):
        for name, value in expected.items():
            assert decoded[name] == value


def test_clean_fixture_has_no_corruption(fixture_file):
    _, data, _, _ = fixture_file
    for log in decode_bytes(data):
        assert log.stats.frames_corrupt == {}
        assert log.stats.bytes_skipped_resync == 0
        assert log.stats.log_end_marker_found is True


def test_frame_offsets_point_at_frame_markers(fixture_file):
    _, data, _, _ = fixture_file
    for log in decode_bytes(data):
        for frame in log.main_frames:
            assert data[frame["_file_offset"]] == ord(frame["_frame_type"])


def _flip(data, offset):
    damaged = bytearray(data)
    damaged[offset] ^= 0xFF
    return bytes(damaged)


def test_structural_corruption_is_detected_and_counted(fixture_file):
    _, data, truths, _ = fixture_file
    log = decode_bytes(data)[0]
    dlog = decode_bytes(_flip(data, log.main_frames[40]["_file_offset"] + 2))[0]
    assert sum(dlog.stats.frames_corrupt.values()) + dlog.stats.bytes_skipped_resync > 0
    expected = {f["loopIteration"]: f for f in truths[0]["main"]}
    for frame in dlog.main_frames:
        assert frame["time"] == expected[frame["loopIteration"]]["time"]
    assert len(dlog.main_frames) < len(truths[0]["main"])


def test_undetectable_corruption_is_bounded_by_next_i_frame(fixture_file):
    """
    Blackbox has no checksums. A flipped byte that still decodes to a
    well-formed frame yields wrong values until the next I-frame. This
    test documents that limit: values are exact again from the next
    I-frame onward (I interval = 32 in the fixture).
    """
    _, data, truths, _ = fixture_file
    log = decode_bytes(data)[0]
    dlog = decode_bytes(_flip(data, log.main_frames[40]["_file_offset"] + 3))[0]
    expected = {f["loopIteration"]: f for f in truths[0]["main"]}
    wrong = [f["loopIteration"] for f in dlog.main_frames
             if any(f[k] != expected[f["loopIteration"]][k] for k in expected[0])]
    assert wrong, "fixture no longer exercises the undetectable case"
    assert max(wrong) < 64  # next I-frame is iteration 64
    assert all(f == expected[f["loopIteration"]] or f["loopIteration"] < 64
               for f in [{k: v for k, v in fr.items() if not k.startswith("_")}
                         for fr in dlog.main_frames])


def test_truncated_file_does_not_crash(fixture_file):
    _, data, _, log0_len = fixture_file
    logs = decode_bytes(data[: log0_len // 2])
    assert len(logs) == 1
    assert len(logs[0].main_frames) > 0


# ------------------------------------------------------- normalized mapping
def test_metadata(fixture_file):
    path, *_ = fixture_file
    meta = EmuFlightBlackboxParser(path).extract_metadata()
    assert meta.platform == "EmuFlight"
    assert meta.firmware_version == "0.4.1"
    assert meta.vehicle_type is None
    assert meta.metadata["log_count"] == 2
    assert meta.metadata["craft_name"] == "TESTQUAD"
    assert meta.metadata["overlapping_log_time_ranges"] is False


def test_gps_records_scaled_and_traceable(fixture_file):
    path, _, truths, _ = fixture_file
    gps = EmuFlightBlackboxParser(path).extract_gps()
    assert len(gps) == len(truths[0]["gps"])
    first, expected = gps[0], truths[0]["gps"][0]
    assert first.latitude == pytest.approx(expected["GPS_coord[0]"] * 1e-7)
    assert first.longitude == pytest.approx(expected["GPS_coord[1]"] * 1e-7)
    assert first.timestamp == pytest.approx(expected["time"] * 1e-6)
    assert first.speed_m_s == pytest.approx(expected["GPS_speed"] * 0.01)
    assert first.altitude_m is None                     # unit not verified -> not guessed
    assert first.raw["GPS_altitude"] == expected["GPS_altitude"]
    assert first.fix_type is None and first.hdop is None  # not in the log
    assert first.raw["file_offset"] is not None
    assert abs(first.latitude - HOME[0] * 1e-7) < 1e-3


def test_altitude_scale_is_opt_in(fixture_file):
    path, *_ = fixture_file
    units = EmuFlightUnitConfig(gps_altitude_scale_m=0.01)
    gps = EmuFlightBlackboxParser(path, units=units).extract_gps()
    assert gps[0].altitude_m == pytest.approx(12.34)


def test_states_capture_every_transition_and_dedupe(fixture_file):
    path, *_ = fixture_file
    states = EmuFlightBlackboxParser(path, log_index=0).extract_states()
    slow = [s for s in states if s.raw["blackbox_frame_type"] == "S"]
    assert len(slow) == 3  # initial, RX loss, recovery; identical 4th is dropped
    assert [s.failsafe for s in slow] == [False, True, False]
    disarms = [s for s in states if s.armed is False]
    assert len(disarms) == 1 and disarms[0].raw["disarm_reason_code"] == 4
    assert all(s.armed in (None, False) for s in states)  # armed=True never assumed


def test_failsafe_records(fixture_file):
    path, *_ = fixture_file
    fs = EmuFlightBlackboxParser(path, log_index=0).extract_failsafe()
    assert [f.manual_control_signal_lost for f in fs] == [False, True, False]


def test_unavailable_categories_are_empty_not_invented(fixture_file):
    path, *_ = fixture_file
    parser = EmuFlightBlackboxParser(path)
    assert parser.extract_navigation() == []
    assert parser.extract_commands() == []
    assert parser.extract_command_acks() == []
    assert parser.extract_telemetry() == []
    assert parser.extract_battery() == []  # vbat unit not verified


def test_events_and_parameters(fixture_file):
    path, _, truths, _ = fixture_file
    parser = EmuFlightBlackboxParser(path)

    events = parser.extract_events()
    names = [e.event_type for e in events]

    assert names.count("DISARM") == 2 and names.count("LOG_END") == 2

    adj = next(
        e for e in events
        if e.event_type == "INFLIGHT_ADJUSTMENT"
    )

    assert adj.data["new_value"] == pytest.approx(0.5)

    params = {
        p.name: p.value
        for p in parser.extract_parameters()
        if p.raw["log_index"] == 0
    }

    assert params["rates"] == "70,70,70"
    assert not any(name.startswith("Field ") for name in params)


def test_log_index_selection(fixture_file):
    path, _, truths, _ = fixture_file
    only_second = EmuFlightBlackboxParser(path, log_index=1)
    assert only_second.extract_metadata().metadata["log_count"] == 1
    assert only_second.extract_gps() == []
