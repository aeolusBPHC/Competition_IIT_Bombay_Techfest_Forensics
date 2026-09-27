from pathlib import Path

from platform_parsers.ardupilot.dataflash_parser import (
    ArduPilotDataFlashParser,
)


FIXTURE = Path(
    "tests/fixtures/synthetic_ardupilot_forensics.bin"
)


def test_ardupilot_dataflash_identification():
    result = ArduPilotDataFlashParser.identify(FIXTURE)

    assert result["supported"] is True
    assert result["platform"] == "ArduPilot"
    assert result["format"] == "DataFlash"
    assert result["confidence"] == "HIGH"


def test_ardupilot_dataflash_record_counts():
    parser = ArduPilotDataFlashParser(FIXTURE)

    evidence = parser.parse()

    assert len(evidence.gps) == 2
    assert len(evidence.commands) == 1
    assert len(evidence.command_acks) == 0
    assert len(evidence.states) == 2
    assert len(evidence.parameters) == 1
    assert len(evidence.events) == 2

def test_navigation_record_count():
    parser = ArduPilotDataFlashParser(FIXTURE)

    navigation = parser.extract_navigation()

    assert len(navigation) == 2


def test_navigation_values():
    parser = ArduPilotDataFlashParser(FIXTURE)

    navigation = parser.extract_navigation()

    first = navigation[0]
    second = navigation[1]

    assert first.timestamp == 1.5
    assert first.latitude == 47.397945
    assert first.longitude == 8.546176
    assert abs(first.altitude_m - 230.5) < 1e-6
    assert abs(first.delta_altitude_m - 2.35) < 1e-5

    assert second.timestamp == 2.5
    assert second.latitude == 47.3979452
    assert second.longitude == 8.5461762
    assert abs(second.altitude_m - 231.5) < 1e-6
    assert abs(second.delta_altitude_m - 2.45) < 1e-5


def test_navigation_metadata():
    parser = ArduPilotDataFlashParser(FIXTURE)

    navigation = parser.extract_navigation()

    first = navigation[0]

    assert first.source_platform == "ArduPilot"

    assert first.raw["dataset"] == "POS"

    assert first.raw["relative_origin_altitude"] == (
        first.raw["raw_fields"]["RelOriginAlt"]
    )


def test_parse_includes_navigation():
    parser = ArduPilotDataFlashParser(FIXTURE)

    evidence = parser.parse()

    assert len(evidence.navigation) == 2


def test_ardupilot_gps_values():
    parser = ArduPilotDataFlashParser(FIXTURE)

    evidence = parser.parse()

    assert len(evidence.gps) == 2

    first = evidence.gps[0]
    second = evidence.gps[1]

    assert abs(first.latitude - 47.397945) < 1e-7
    assert abs(first.longitude - 8.546176) < 1e-7
    assert abs(first.altitude_m - 230.0) < 0.01
    assert abs(first.speed_m_s - 0.5) < 0.01

    assert abs(second.latitude - 47.3979451) < 1e-7
    assert abs(second.longitude - 8.5461761) < 1e-7
    assert abs(second.altitude_m - 231.0) < 0.01
    assert abs(second.speed_m_s - 0.75) < 0.01


def test_ardupilot_command():
    parser = ArduPilotDataFlashParser(FIXTURE)

    evidence = parser.parse()

    assert len(evidence.commands) == 1

    command = evidence.commands[0]

    assert command.command_id == 400
    assert command.source_system == 255
    assert command.source_component == 190
    assert command.target_system == 1
    assert command.target_component == 1


def test_ardupilot_states():
    parser = ArduPilotDataFlashParser(FIXTURE)

    evidence = parser.parse()

    assert len(evidence.states) == 2

    mode_state = evidence.states[0]
    arm_state = evidence.states[1]

    assert mode_state.flight_mode == 4
    assert arm_state.armed == 1


def test_ardupilot_parameter():
    parser = ArduPilotDataFlashParser(FIXTURE)

    evidence = parser.parse()

    assert len(evidence.parameters) == 1

    parameter = evidence.parameters[0]

    assert parameter.name == "GPS_TYPE"
    assert parameter.value == 1.0


def test_ardupilot_events():
    parser = ArduPilotDataFlashParser(FIXTURE)

    evidence = parser.parse()

    assert len(evidence.events) == 2

    assert evidence.events[0].event_type == "EV"
    assert evidence.events[1].event_type == "ERR"

def test_ardupilot_battery_record_count():
    parser = ArduPilotDataFlashParser(
        FIXTURE
    )

    battery = parser.extract_battery()

    assert len(battery) == 2


def test_ardupilot_battery_first_record():
    parser = ArduPilotDataFlashParser(
        FIXTURE
    )

    battery = parser.extract_battery()

    record = battery[0]

    assert record.timestamp == 1.75
    assert abs(record.voltage_v - 16.20) < 1e-5
    assert abs(record.current_a - 2.50) < 1e-5
    assert abs(record.discharged_mah - 12.50) < 1e-5
    assert abs(record.temperature_c - 25.0) < 1e-5
    assert abs(record.remaining - 0.98) < 1e-5

    assert record.source_platform == "ArduPilot"


def test_ardupilot_battery_second_record():
    parser = ArduPilotDataFlashParser(
        FIXTURE
    )

    battery = parser.extract_battery()

    record = battery[1]

    assert record.timestamp == 2.75
    assert abs(record.voltage_v - 16.05) < 1e-5
    assert abs(record.current_a - 4.00) < 1e-5
    assert abs(record.discharged_mah - 18.75) < 1e-5
    assert abs(record.temperature_c - 26.5) < 1e-5
    assert abs(record.remaining - 0.96) < 1e-5

    assert record.source_platform == "ArduPilot"


def test_ardupilot_battery_preserves_raw_data():
    parser = ArduPilotDataFlashParser(
        FIXTURE
    )

    battery = parser.extract_battery()

    record = battery[0]

    assert record.raw["dataset"] == "BAT"
    assert record.raw["message_type"] == 9
    assert record.raw["timestamp_raw"] == 1_750_000

    assert record.raw["fields"]["Volt"] == record.voltage_v
    assert record.raw["fields"]["Curr"] == record.current_a
    assert record.raw["fields"]["Temp"] == record.temperature_c
