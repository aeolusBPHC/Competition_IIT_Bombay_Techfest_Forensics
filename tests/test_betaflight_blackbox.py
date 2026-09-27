from pathlib import Path

import pytest

from platform_parsers.betaflight.blackbox_parser import (
    BetaflightBlackboxParser,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "synthetic_betaflight_blackbox.bbl"
)


def test_fixture_exists():
    assert FIXTURE.exists()
    assert FIXTURE.is_file()


def test_identify_betaflight_blackbox():
    result = BetaflightBlackboxParser.identify(FIXTURE)

    assert result["supported"] is True
    assert result["platform"] == "Betaflight"
    assert result["format"] == "BLACKBOX"
    assert result["confidence"] == "HIGH"

    assert result["indicators"]["marker_detected"] is True
    assert result["indicators"]["firmware_type"] == "Betaflight"
    assert result["indicators"]["data_version"] == "2"


def test_metadata():
    parser = BetaflightBlackboxParser(FIXTURE)

    metadata = parser.get_metadata()

    assert metadata.platform == "Betaflight"
    assert metadata.format == "BLACKBOX"
    assert metadata.firmware == "Betaflight"
    assert metadata.firmware_version == "4.5.0"

    assert "GPS_coord[0]" in metadata.metadata["gps_fields"]
    assert "GPS_coord[1]" in metadata.metadata["gps_fields"]

    assert "GPS_home[0]" in metadata.metadata["home_fields"]
    assert "GPS_home[1]" in metadata.metadata["home_fields"]


def test_gps_record_count():
    parser = BetaflightBlackboxParser(FIXTURE)

    gps = parser.extract_gps()

    assert len(gps) == 2


def test_first_gps_record():
    parser = BetaflightBlackboxParser(FIXTURE)

    gps = parser.extract_gps()
    first = gps[0]

    assert first.timestamp == pytest.approx(1.0)

    assert first.latitude == pytest.approx(
        47.397945,
        abs=1e-9,
    )

    assert first.longitude == pytest.approx(
        8.546176,
        abs=1e-9,
    )

    assert first.altitude_m == pytest.approx(
        230.0
    )

    assert first.speed_m_s == pytest.approx(
        5.0
    )

    assert first.heading_deg == pytest.approx(
        90.0
    )

    assert first.satellites == 10

    assert first.source_platform == "Betaflight"


def test_second_gps_record():
    parser = BetaflightBlackboxParser(FIXTURE)

    gps = parser.extract_gps()
    second = gps[1]

    assert second.timestamp == pytest.approx(2.0)

    assert second.latitude == pytest.approx(
        47.397946,
        abs=1e-9,
    )

    assert second.longitude == pytest.approx(
        8.546178,
        abs=1e-9,
    )

    assert second.altitude_m == pytest.approx(
        231.0
    )

    assert second.speed_m_s == pytest.approx(
        7.5
    )

    assert second.heading_deg == pytest.approx(
        92.0
    )

    assert second.satellites == 11


def test_gps_raw_values_preserved():
    parser = BetaflightBlackboxParser(FIXTURE)

    gps = parser.extract_gps()

    first = gps[0]

    assert first.raw["GPS_numSat"] == 10
    assert first.raw["GPS_coord[0]"] == 473979450
    assert first.raw["GPS_coord[1]"] == 85461760
    assert first.raw["GPS_altitude"] == 2300
    assert first.raw["GPS_speed"] == 500
    assert first.raw["GPS_ground_course"] == 900

def test_navigation_record_count():
    parser = BetaflightBlackboxParser(FIXTURE)

    navigation = parser.extract_navigation()

    assert len(navigation) == 2


def test_navigation_values():
    parser = BetaflightBlackboxParser(FIXTURE)

    navigation = parser.extract_navigation()

    first = navigation[0]
    second = navigation[1]

    assert first.timestamp == pytest.approx(1.0)

    assert first.latitude == pytest.approx(
        47.397945,
        abs=1e-9,
    )

    assert first.longitude == pytest.approx(
        8.546176,
        abs=1e-9,
    )

    assert first.altitude_m == pytest.approx(
        230.0
    )

    assert first.delta_altitude_m is None

    assert first.source_platform == "Betaflight"

    assert second.timestamp == pytest.approx(2.0)

    assert second.latitude == pytest.approx(
        47.397946,
        abs=1e-9,
    )

    assert second.longitude == pytest.approx(
        8.546178,
        abs=1e-9,
    )

    assert second.altitude_m == pytest.approx(
        231.0
    )

    assert second.delta_altitude_m is None


def test_navigation_raw_values_preserved():
    parser = BetaflightBlackboxParser(FIXTURE)

    navigation = parser.extract_navigation()

    first = navigation[0]

    assert first.raw["dataset"] == "G"
    assert first.raw["time"] == 1_000_000
    assert first.raw["GPS_numSat"] == 10
    assert first.raw["GPS_coord[0]"] == 473979450
    assert first.raw["GPS_coord[1]"] == 85461760
    assert first.raw["GPS_altitude"] == 2300
    assert first.raw["GPS_speed"] == 500
    assert first.raw["GPS_ground_course"] == 900

def test_parse_returns_normalized_evidence():
    parser = BetaflightBlackboxParser(FIXTURE)

    evidence = parser.parse()

    assert evidence.metadata.platform == "Betaflight"
    assert evidence.metadata.format == "BLACKBOX"

    assert len(evidence.gps) == 2

    assert evidence.gps[0].latitude == pytest.approx(
        47.397945,
        abs=1e-9,
    )


def test_unsupported_sections_are_empty():
    parser = BetaflightBlackboxParser(FIXTURE)

    assert parser.extract_commands() == []
    assert parser.extract_command_acks() == []
    assert parser.extract_states() == []
    assert parser.extract_parameters() == []
    assert parser.extract_events() == []

def test_betaflight_does_not_claim_inav_blackbox():
    inav_fixture = (
        Path(__file__).parent
        / "fixtures"
        / "synthetic_inav_blackbox.bbl"
    )

    detection = BetaflightBlackboxParser.identify(
        inav_fixture
    )

    assert detection["supported"] is False


def test_betaflight_normalized_api_is_complete():
    parser = BetaflightBlackboxParser(FIXTURE)

    evidence = parser.parse()

    assert hasattr(evidence, "metadata")
    assert hasattr(evidence, "gps")
    assert hasattr(evidence, "navigation")
    assert hasattr(evidence, "battery")
    assert hasattr(evidence, "telemetry")
    assert hasattr(evidence, "failsafe")
    assert hasattr(evidence, "commands")
    assert hasattr(evidence, "command_acks")
    assert hasattr(evidence, "states")
    assert hasattr(evidence, "parameters")
    assert hasattr(evidence, "events")
    assert hasattr(evidence, "additional_data")


def test_betaflight_unsupported_normalized_categories_are_explicitly_empty():
    parser = BetaflightBlackboxParser(FIXTURE)

    assert parser.extract_telemetry() == []
    assert parser.extract_failsafe() == []
    assert parser.extract_commands() == []
    assert parser.extract_command_acks() == []
    assert parser.extract_states() == []
    assert parser.extract_parameters() == []
    assert parser.extract_events() == []
