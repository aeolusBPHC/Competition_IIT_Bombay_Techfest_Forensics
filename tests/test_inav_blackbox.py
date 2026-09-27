from pathlib import Path

import pytest

from platform_parsers.inav.blackbox_parser import (
    INAVBlackboxParser,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "synthetic_inav_blackbox.bbl"
)


def test_fixture_exists():
    assert FIXTURE.exists()
    assert FIXTURE.is_file()


def test_identify_inav_blackbox():

    result = INAVBlackboxParser.identify(
        FIXTURE
    )

    assert result["supported"] is True
    assert result["platform"] == "INAV"
    assert result["format"] == "BLACKBOX"
    assert result["confidence"] == "HIGH"

    assert (
        result["indicators"]["firmware_type"]
        == "INAV"
    )

    assert (
        result["indicators"]["data_version"]
        == "2"
    )


def test_metadata():

    parser = INAVBlackboxParser(
        FIXTURE
    )

    metadata = parser.get_metadata()

    assert metadata.platform == "INAV"
    assert metadata.format == "BLACKBOX"
    assert metadata.firmware == "INAV"
    assert metadata.firmware_version == "7.1.0"

    assert (
        "GPS_coord[0]"
        in metadata.metadata["gps_fields"]
    )

    assert (
        "GPS_coord[1]"
        in metadata.metadata["gps_fields"]
    )

    assert (
        "GPS_home[0]"
        in metadata.metadata["home_fields"]
    )


def test_gps_record_count():

    parser = INAVBlackboxParser(
        FIXTURE
    )

    gps = parser.extract_gps()

    assert len(gps) == 2


def test_first_gps_record():

    parser = INAVBlackboxParser(
        FIXTURE
    )

    first = parser.extract_gps()[0]

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

    assert first.fix_type == 3
    assert first.satellites == 10


def test_second_gps_record():

    parser = INAVBlackboxParser(
        FIXTURE
    )

    second = parser.extract_gps()[1]

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

    assert second.fix_type == 3
    assert second.satellites == 12


def test_raw_fields_are_preserved():

    parser = INAVBlackboxParser(
        FIXTURE
    )

    first = parser.extract_gps()[0]

    assert first.raw["GPS_fixType"] == 3
    assert first.raw["GPS_numSat"] == 10

    assert (
        first.raw["GPS_coord[0]"]
        == 473979450
    )

    assert (
        first.raw["GPS_coord[1]"]
        == 85461760
    )

    assert (
        first.raw["GPS_altitude"]
        == 230
    )

    assert (
        first.raw["GPS_speed"]
        == 500
    )

    assert (
        first.raw["GPS_ground_course"]
        == 900
    )


def test_navigation_record_count():
    parser = INAVBlackboxParser(FIXTURE)

    navigation = parser.extract_navigation()

    assert len(navigation) == 2


def test_navigation_values():
    parser = INAVBlackboxParser(FIXTURE)

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

    assert first.source_platform == "INAV"

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
    parser = INAVBlackboxParser(FIXTURE)

    navigation = parser.extract_navigation()

    first = navigation[0]
    second = navigation[1]

    assert first.raw["dataset"] == "G"

    assert first.raw["time"] == 1_000_000
    assert first.raw["GPS_fixType"] == 3
    assert first.raw["GPS_numSat"] == 10

    assert first.raw["GPS_coord[0]"] == 473979450
    assert first.raw["GPS_coord[1]"] == 85461760

    assert first.raw["GPS_altitude"] == 230
    assert first.raw["GPS_speed"] == 500
    assert first.raw["GPS_ground_course"] == 900

    assert first.raw["GPS_velned[0]"] == 300
    assert first.raw["GPS_velned[1]"] == 400
    assert first.raw["GPS_velned[2]"] == 0

    assert first.raw["GPS_time"] == 12_000

    assert second.raw["GPS_numSat"] == 12
    assert second.raw["GPS_velned[0]"] == 500
    assert second.raw["GPS_velned[1]"] == 600
    assert second.raw["GPS_velned[2]"] == -50

def test_velocity_fields_are_preserved():

    parser = INAVBlackboxParser(
        FIXTURE
    )

    first = parser.extract_gps()[0]

    assert first.raw["GPS_velned[0]"] == 300
    assert first.raw["GPS_velned[1]"] == 400
    assert first.raw["GPS_velned[2]"] == 0


def test_parse_returns_normalized_evidence():

    parser = INAVBlackboxParser(
        FIXTURE
    )

    evidence = parser.parse()

    assert (
        evidence.metadata.platform
        == "INAV"
    )

    assert (
        evidence.metadata.format
        == "BLACKBOX"
    )

    assert len(evidence.gps) == 2


def test_unsupported_sections_are_empty():

    parser = INAVBlackboxParser(
        FIXTURE
    )

    assert parser.extract_commands() == []
    assert parser.extract_command_acks() == []
    assert parser.extract_states() == []
    assert parser.extract_parameters() == []
    assert parser.extract_events() == []

def test_inav_does_not_claim_betaflight_blackbox():
    betaflight_fixture = (
        Path(__file__).parent
        / "fixtures"
        / "synthetic_betaflight_blackbox.bbl"
    )

    detection = INAVBlackboxParser.identify(
        betaflight_fixture
    )

    assert detection["supported"] is False


def test_inav_normalized_api_is_complete():
    parser = INAVBlackboxParser(FIXTURE)

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


def test_inav_unsupported_normalized_categories_are_explicitly_empty():
    parser = INAVBlackboxParser(FIXTURE)

    assert parser.extract_battery() == []
    assert parser.extract_telemetry() == []
    assert parser.extract_failsafe() == []
    assert parser.extract_commands() == []
    assert parser.extract_command_acks() == []
    assert parser.extract_states() == []
    assert parser.extract_parameters() == []
    assert parser.extract_events() == []
