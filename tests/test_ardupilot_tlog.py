from pathlib import Path

from platform_parsers.ardupilot.tlog_parser import ArduPilotTLogParser
from platform_parsers.common.evidence_model import NormalizedEvidence


FIXTURE = Path("tests/fixtures/synthetic_mavlink_gps.tlog")
ARDUPILOT_FIXTURE = Path(
    "tests/fixtures/synthetic_ardupilot.tlog"
)

def test_ardupilot_tlog_identification():
    result = ArduPilotTLogParser.identify(FIXTURE)

    # The fixture is a valid MAVLink TLOG, but it does not
    # contain ArduPilot-specific platform evidence.
    assert result["supported"] is False
    assert result["platform"] == "ArduPilot"
    assert result["format"] == "TLOG"
    assert result["confidence"] == "NONE"

    assert result["indicators"]["records_detected"] == 6
    assert result["indicators"]["mavlink_versions"] == ["MAVLink 1"]

    assert result["indicators"]["message_types"] == [
        "GPS_RAW_INT",
        "GPS_RAW_INT",
        "GLOBAL_POSITION_INT",
        "GLOBAL_POSITION_INT",
        "BATTERY_STATUS",
        "BATTERY_STATUS",
    ]

    assert result["platform_evidence"]["ardupilot"] is False
    assert result["platform_evidence"]["heartbeat_detected"] is False
    assert result["platform_evidence"]["autopilot_values"] == []
    assert result["platform_evidence"]["custom_mode_values"] == []

def test_ardupilot_tlog_identification_with_ardupilot_evidence():
    result = ArduPilotTLogParser.identify(ARDUPILOT_FIXTURE)

    assert result["supported"] is True
    assert result["platform"] == "ArduPilot"
    assert result["format"] == "TLOG"
    assert result["confidence"] == "HIGH"

    assert result["platform_evidence"]["ardupilot"] is True
    assert result["platform_evidence"]["heartbeat_detected"] is True
    assert result["platform_evidence"]["autopilot_values"] == [3]
    assert result["platform_evidence"]["custom_mode_values"] == [0]

    assert result["indicators"]["records_detected"] == 4
    assert result["indicators"]["mavlink_versions"] == ["MAVLink 1"]

    assert result["indicators"]["message_types"] == [
        "HEARTBEAT",
        "GPS_RAW_INT",
        "GPS_RAW_INT",
        "BATTERY_STATUS",
    ]

def test_ardupilot_tlog_record_count():
    parser = ArduPilotTLogParser(FIXTURE)

    records = list(parser._iter_tlog())

    assert len(records) == 6


def test_ardupilot_tlog_message_types():
    parser = ArduPilotTLogParser(FIXTURE)

    records = list(parser._iter_tlog())

    message_types = [
        record["message"].get_type()
        for record in records
    ]

    assert message_types == [
        "GPS_RAW_INT",
        "GPS_RAW_INT",
        "GLOBAL_POSITION_INT",
        "GLOBAL_POSITION_INT",
         "BATTERY_STATUS",
         "BATTERY_STATUS",
    ]


def test_ardupilot_tlog_gps_raw_int():
    parser = ArduPilotTLogParser(FIXTURE)

    gps_records = parser.extract_gps()

    assert len(gps_records) == 4

    gps = gps_records[0]

    assert gps.timestamp == 1700000000.0
    assert gps.latitude == 47.397945
    assert gps.longitude == 8.546176
    assert gps.altitude_m == 230.0
    assert gps.speed_m_s == 0.5

    assert gps.fix_type == 3
    assert gps.satellites == 10

    assert gps.hdop == 0.7
    assert gps.vdop == 0.8
    assert gps.heading_deg == 90.0

    assert gps.source_platform == "ArduPilot"


def test_ardupilot_tlog_second_gps_raw_int():
    parser = ArduPilotTLogParser(FIXTURE)

    gps_records = parser.extract_gps()

    gps = gps_records[1]

    assert gps.timestamp == 1700000001.0
    assert gps.latitude == 47.3979451
    assert gps.longitude == 8.5461761
    assert gps.altitude_m == 231.0
    assert gps.speed_m_s == 0.75

    assert gps.fix_type == 3
    assert gps.satellites == 11

    assert gps.hdop == 0.65
    assert gps.vdop == 0.75
    assert gps.heading_deg == 92.0


def test_ardupilot_tlog_global_position_int():
    parser = ArduPilotTLogParser(FIXTURE)

    gps_records = parser.extract_gps()

    gps = gps_records[2]

    assert gps.timestamp == 1700000002.0
    assert gps.latitude == 47.397946
    assert gps.longitude == 8.546177
    assert gps.altitude_m == 232.0

    # vx = 1.0 m/s
    # vy = 2.0 m/s
    # horizontal speed = sqrt(vx^2 + vy^2)
    expected_speed = (1.0**2 + 2.0**2) ** 0.5

    assert gps.speed_m_s == expected_speed

    assert gps.heading_deg == 95.0

    # GLOBAL_POSITION_INT does not directly provide these fields.
    assert gps.fix_type is None
    assert gps.satellites is None
    assert gps.hdop is None
    assert gps.vdop is None


def test_ardupilot_tlog_second_global_position_int():
    parser = ArduPilotTLogParser(FIXTURE)

    gps_records = parser.extract_gps()

    gps = gps_records[3]

    assert gps.timestamp == 1700000003.0
    assert gps.latitude == 47.3979461
    assert gps.longitude == 8.5461771
    assert gps.altitude_m == 233.0

    # vx = 1.5 m/s
    # vy = 2.5 m/s
    expected_speed = (1.5**2 + 2.5**2) ** 0.5

    assert gps.speed_m_s == expected_speed

    assert gps.heading_deg == 97.0


def test_ardupilot_tlog_outer_timestamp_is_used():
    parser = ArduPilotTLogParser(FIXTURE)

    records = list(parser._iter_tlog())

    first_message = records[0]["message"]

    # The TLOG timestamp is the forensic record timestamp.
    assert records[0]["timestamp"] == 1700000000.0

    # The MAVLink GPS message has its own internal timestamp.
    assert first_message.time_usec != records[0]["timestamp"]


def test_ardupilot_tlog_raw_data_preserved():
    parser = ArduPilotTLogParser(FIXTURE)

    gps_records = parser.extract_gps()

    gps_raw = gps_records[0]

    assert gps_raw.raw["mavpackettype"] == "GPS_RAW_INT"

    assert gps_raw.raw["lat"] == 473979450
    assert gps_raw.raw["lon"] == 85461760
    assert gps_raw.raw["alt"] == 230000

    global_position = gps_records[2]

    assert global_position.raw["mavpackettype"] == "GLOBAL_POSITION_INT"

    assert global_position.raw["lat"] == 473979460
    assert global_position.raw["lon"] == 85461770
    assert global_position.raw["alt"] == 232000

def test_ardupilot_tlog_navigation():
    parser = ArduPilotTLogParser(FIXTURE)

    navigation_records = parser.extract_navigation()

    assert len(navigation_records) == 2

    navigation = navigation_records[0]

    assert navigation.timestamp == 1700000002.0

    assert navigation.latitude == 47.397946
    assert navigation.longitude == 8.546177

    assert navigation.altitude_m == 232.0

    assert navigation.delta_altitude_m == 12.0

    assert navigation.source_platform == "ArduPilot"


def test_ardupilot_tlog_second_navigation():
    parser = ArduPilotTLogParser(FIXTURE)

    navigation_records = parser.extract_navigation()

    navigation = navigation_records[1]

    assert navigation.timestamp == 1700000003.0

    assert navigation.latitude == 47.3979461
    assert navigation.longitude == 8.5461771

    assert navigation.altitude_m == 233.0

    assert navigation.delta_altitude_m == 13.0


def test_ardupilot_tlog_navigation_raw_data():
    parser = ArduPilotTLogParser(FIXTURE)

    navigation_records = parser.extract_navigation()

    navigation = navigation_records[0]

    assert navigation.raw["mavpackettype"] == (
        "GLOBAL_POSITION_INT"
    )

    assert navigation.raw["lat"] == 473979460
    assert navigation.raw["lon"] == 85461770
    assert navigation.raw["alt"] == 232000

    assert navigation.raw["relative_alt"] == 12000

    assert navigation.raw["vx"] == 100
    assert navigation.raw["vy"] == 200
    assert navigation.raw["vz"] == -50

    assert navigation.raw["hdg"] == 9500


def test_ardupilot_tlog_navigation_excludes_raw_gps():
    parser = ArduPilotTLogParser(FIXTURE)

    navigation_records = parser.extract_navigation()

    for navigation in navigation_records:
        assert navigation.raw["mavpackettype"] == (
            "GLOBAL_POSITION_INT"
        )


def test_ardupilot_tlog_parse_returns_normalized_evidence():
    parser = ArduPilotTLogParser(FIXTURE)

    evidence = parser.parse()

    assert isinstance(evidence, NormalizedEvidence)

    assert evidence.metadata.platform == "ArduPilot"
    assert evidence.metadata.format == "TLOG"

    assert len(evidence.gps) == 4

    assert evidence.gps[0].latitude == 47.397945
    assert evidence.gps[0].longitude == 8.546176

def test_ardupilot_tlog_battery_record_count():
    parser = ArduPilotTLogParser(FIXTURE)

    battery = parser.extract_battery()

    assert len(battery) == 2


def test_ardupilot_tlog_battery_values():
    parser = ArduPilotTLogParser(FIXTURE)

    battery = parser.extract_battery()

    first = battery[0]
    second = battery[1]

    assert first.timestamp == 1700000004.0
    assert abs(first.voltage_v - 16.20) < 0.001
    assert abs(first.current_a - 2.50) < 0.001
    assert abs(first.discharged_mah - 12500.0) < 0.001
    assert abs(first.remaining - 0.98) < 0.001
    assert abs(first.temperature_c - 25.0) < 0.001
    assert first.cell_count == 4
    assert first.source_platform == "ArduPilot"

    assert second.timestamp == 1700000005.0
    assert abs(second.voltage_v - 16.05) < 0.001
    assert abs(second.current_a - 4.0) < 0.001
    assert abs(second.discharged_mah - 12518.0) < 0.001
    assert abs(second.remaining - 0.96) < 0.001
    assert abs(second.temperature_c - 26.5) < 0.001
    assert second.cell_count == 4


def test_ardupilot_tlog_battery_raw_data():
    parser = ArduPilotTLogParser(FIXTURE)

    battery = parser.extract_battery()

    record = battery[0]

    assert record.raw["mavpackettype"] == (
        "BATTERY_STATUS"
    )

    assert record.raw["message"]["id"] == 1
    assert record.raw["message"]["temperature"] == 2500
    assert record.raw["message"]["current_battery"] == 250
    assert record.raw["message"]["current_consumed"] == 12500
    assert record.raw["message"]["battery_remaining"] == 98


def test_ardupilot_tlog_states_from_heartbeat():
    parser = ArduPilotTLogParser(ARDUPILOT_FIXTURE)

    states = parser.extract_states()

    assert len(states) == 1

    state = states[0]

    assert state.source_platform == "ArduPilot"
    assert state.armed is False
    assert state.flight_mode == "Mode(0x00000000)"
    assert state.failsafe is None

    assert state.raw["mavpackettype"] == "HEARTBEAT"
    assert state.raw["base_mode"] == 0
    assert state.raw["custom_mode"] == 0
    assert state.raw["system_status"] == 4
