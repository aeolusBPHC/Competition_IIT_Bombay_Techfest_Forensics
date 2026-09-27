from pathlib import Path

from platform_parsers.mavlink.tlog_parser import (
    MAVLinkTLogParser,
)


FIXTURE = Path(
    "tests/fixtures/synthetic_mavlink_gps.tlog"
)


def test_mavlink_tlog_identification():
    result = MAVLinkTLogParser.identify(FIXTURE)

    assert result["supported"] is True
    assert result["platform"] == "MAVLink"
    assert result["format"] == "TLOG"
    assert result["confidence"] == "LOW"

    assert result["indicators"]["records_detected"] == 6

    assert (
        result["indicators"]["message_types"]
        == [
            "GPS_RAW_INT",
            "GPS_RAW_INT",
            "GLOBAL_POSITION_INT",
            "GLOBAL_POSITION_INT",
            "BATTERY_STATUS",
            "BATTERY_STATUS",
        ]
    )


def test_mavlink_tlog_record_counts():
    parser = MAVLinkTLogParser(FIXTURE)

    evidence = parser.parse()

    assert len(evidence.gps) == 4
    assert len(evidence.navigation) == 2
    assert len(evidence.battery) == 2

    assert len(evidence.commands) == 0
    assert len(evidence.command_acks) == 0
    assert len(evidence.states) == 0
    assert len(evidence.parameters) == 0
    assert len(evidence.events) == 0


def test_mavlink_tlog_gps_raw_int_values():
    """
    Verify GPS_RAW_INT normalization.
    """

    parser = MAVLinkTLogParser(FIXTURE)

    evidence = parser.parse()

    first = evidence.gps[0]
    second = evidence.gps[1]

    # --------------------------------------------------
    # First GPS_RAW_INT record
    # --------------------------------------------------

    assert abs(
        first.latitude - 47.3979450
    ) < 1e-7

    assert abs(
        first.longitude - 8.5461760
    ) < 1e-7

    assert abs(
        first.altitude_m - 230.0
    ) < 0.01

    assert abs(
        first.speed_m_s - 0.50
    ) < 0.01

    assert first.fix_type == 3
    assert first.satellites == 10

    assert abs(
        first.hdop - 0.70
    ) < 0.01

    assert abs(
        first.vdop - 0.80
    ) < 0.01

    assert abs(
        first.heading_deg - 90.0
    ) < 0.01

    # --------------------------------------------------
    # Second GPS_RAW_INT record
    # --------------------------------------------------

    assert abs(
        second.latitude - 47.3979451
    ) < 1e-7

    assert abs(
        second.longitude - 8.5461761
    ) < 1e-7

    assert abs(
        second.altitude_m - 231.0
    ) < 0.01

    assert abs(
        second.speed_m_s - 0.75
    ) < 0.01

    assert second.fix_type == 3
    assert second.satellites == 11

    assert abs(
        second.hdop - 0.65
    ) < 0.01

    assert abs(
        second.vdop - 0.75
    ) < 0.01

    assert abs(
        second.heading_deg - 92.0
    ) < 0.01


def test_mavlink_tlog_global_position_int_values():
    """
    Verify GLOBAL_POSITION_INT normalization.
    """

    parser = MAVLinkTLogParser(FIXTURE)

    evidence = parser.parse()

    third = evidence.gps[2]
    fourth = evidence.gps[3]

    # --------------------------------------------------
    # First GLOBAL_POSITION_INT record
    # --------------------------------------------------

    assert abs(
        third.latitude - 47.3979460
    ) < 1e-7

    assert abs(
        third.longitude - 8.5461770
    ) < 1e-7

    assert abs(
        third.altitude_m - 232.0
    ) < 0.01

    # vx = 2.0 m/s
    # vy = 1.0 m/s
    # speed = sqrt(2^2 + 1^2)
    assert abs(
        third.speed_m_s - 2.236067977
    ) < 1e-6

    assert third.fix_type is None
    assert third.satellites is None
    assert third.hdop is None
    assert third.vdop is None

    assert abs(
        third.heading_deg - 95.0
    ) < 0.01

    # --------------------------------------------------
    # Second GLOBAL_POSITION_INT record
    # --------------------------------------------------

    assert abs(
        fourth.latitude - 47.3979461
    ) < 1e-7

    assert abs(
        fourth.longitude - 8.5461771
    ) < 1e-7

    assert abs(
        fourth.altitude_m - 233.0
    ) < 0.01

    # vx = 2.5 m/s
    # vy = 1.5 m/s
    # speed = sqrt(2.5^2 + 1.5^2)
    assert abs(
        fourth.speed_m_s - 2.915475947
    ) < 1e-6

    assert fourth.fix_type is None
    assert fourth.satellites is None
    assert fourth.hdop is None
    assert fourth.vdop is None

    assert abs(
        fourth.heading_deg - 97.0
    ) < 0.01

def test_mavlink_tlog_navigation_values():
    """
    Verify GLOBAL_POSITION_INT normalization into
    NavigationRecord objects.
    """

    parser = MAVLinkTLogParser(FIXTURE)

    evidence = parser.parse()

    navigation = evidence.navigation

    assert len(navigation) == 2

    # --------------------------------------------------
    # First navigation record
    # --------------------------------------------------

    first = navigation[0]

    assert first.timestamp == 1700000002.0

    assert abs(
        first.latitude - 47.3979460
    ) < 1e-7

    assert abs(
        first.longitude - 8.5461770
    ) < 1e-7

    assert abs(
        first.altitude_m - 232.0
    ) < 0.01

    assert abs(
        first.delta_altitude_m - 12.0
    ) < 0.01

    assert first.source_platform == "MAVLink"

    # --------------------------------------------------
    # Second navigation record
    # --------------------------------------------------

    second = navigation[1]

    assert second.timestamp == 1700000003.0

    assert abs(
        second.latitude - 47.3979461
    ) < 1e-7

    assert abs(
        second.longitude - 8.5461771
    ) < 1e-7

    assert abs(
        second.altitude_m - 233.0
    ) < 0.01

    assert abs(
        second.delta_altitude_m - 13.0
    ) < 0.01

    assert second.source_platform == "MAVLink"


def test_mavlink_tlog_navigation_raw_fields():
    """
    Verify that the complete decoded
    GLOBAL_POSITION_INT message is preserved.
    """

    parser = MAVLinkTLogParser(FIXTURE)

    evidence = parser.parse()

    navigation = evidence.navigation[0]

    assert (
        navigation.raw["mavpackettype"]
        == "GLOBAL_POSITION_INT"
    )

    assert navigation.raw["time_boot_ms"] == 3000

    assert navigation.raw["lat"] == 473979460
    assert navigation.raw["lon"] == 85461770
    assert navigation.raw["alt"] == 232000
    assert navigation.raw["relative_alt"] == 12000

    assert navigation.raw["vx"] == 100
    assert navigation.raw["vy"] == 200
    assert navigation.raw["vz"] == -50

    assert navigation.raw["hdg"] == 9500


def test_mavlink_tlog_navigation_uses_outer_timestamp():
    """
    Verify that NavigationRecord.timestamp comes from
    the TLOG record timestamp.
    """

    parser = MAVLinkTLogParser(FIXTURE)

    evidence = parser.parse()

    first = evidence.navigation[0]
    second = evidence.navigation[1]

    assert first.timestamp == 1700000002.0
    assert second.timestamp == 1700000003.0

    # Internal MAVLink timestamps are preserved separately.
    assert first.raw["time_boot_ms"] == 3000
    assert second.raw["time_boot_ms"] == 4000


def test_mavlink_tlog_uses_tlog_timestamp():
    """
    Verify that normalized GPSRecord.timestamp comes from
    the outer TLOG timestamp rather than the MAVLink
    message's internal timestamp.
    """

    parser = MAVLinkTLogParser(FIXTURE)

    evidence = parser.parse()

    first = evidence.gps[0]
    second = evidence.gps[1]
    third = evidence.gps[2]
    fourth = evidence.gps[3]

    assert first.timestamp == 1700000000.0
    assert second.timestamp == 1700000001.0
    assert third.timestamp == 1700000002.0
    assert fourth.timestamp == 1700000003.0

    # GPS_RAW_INT uses time_usec.
    assert first.raw["time_usec"] == 1_000_000
    assert second.raw["time_usec"] == 2_000_000

    # GLOBAL_POSITION_INT uses time_boot_ms.
    assert third.raw["time_boot_ms"] == 3_000
    assert fourth.raw["time_boot_ms"] == 4_000


def test_mavlink_tlog_preserves_raw_gps_fields():
    """
    Verify that original MAVLink fields are preserved in
    the normalized record's raw dictionary.
    """

    parser = MAVLinkTLogParser(FIXTURE)

    evidence = parser.parse()

    first = evidence.gps[0]

    assert first.raw["mavpackettype"] == "GPS_RAW_INT"
    assert first.raw["lat"] == 473979450
    assert first.raw["lon"] == 85461760
    assert first.raw["alt"] == 230000
    assert first.raw["vel"] == 50
    assert first.raw["cog"] == 9000


def test_mavlink_tlog_preserves_global_position_raw_fields():
    """
    Verify that GLOBAL_POSITION_INT raw fields are preserved.
    """

    parser = MAVLinkTLogParser(FIXTURE)

    evidence = parser.parse()

    third = evidence.gps[2]

    assert (
        third.raw["mavpackettype"]
        == "GLOBAL_POSITION_INT"
    )

    assert third.raw["lat"] == 473979460
    assert third.raw["lon"] == 85461770
    assert third.raw["alt"] == 232000

    assert third.raw["vx"] == 100
    assert third.raw["vy"] == 200
    assert third.raw["hdg"] == 9500


def test_mavlink_tlog_battery_record_count():
    parser = MAVLinkTLogParser(FIXTURE)

    battery = parser.extract_battery()

    assert len(battery) == 2


def test_mavlink_tlog_battery_first_record():
    parser = MAVLinkTLogParser(FIXTURE)

    battery = parser.extract_battery()

    record = battery[0]

    assert record.timestamp == 1700000004.0

    assert abs(
        record.voltage_v - 16.20
    ) < 0.001

    assert abs(
        record.current_a - 2.50
    ) < 0.001

    assert abs(
        record.discharged_mah - 12500.0
    ) < 0.001

    assert abs(
        record.remaining - 0.98
    ) < 0.001

    assert abs(
        record.temperature_c - 25.0
    ) < 0.001

    assert record.cell_count == 4

    assert record.cell_voltages_v == [
        4.05,
        4.05,
        4.05,
        4.05,
    ]

    assert record.max_cell_voltage_delta_v == 0.0

    assert record.source_platform == "MAVLink"


def test_mavlink_tlog_battery_second_record():
    parser = MAVLinkTLogParser(FIXTURE)

    battery = parser.extract_battery()

    record = battery[1]

    assert record.timestamp == 1700000005.0

    assert abs(
        record.voltage_v - 16.05
    ) < 0.001

    assert abs(
        record.current_a - 4.0
    ) < 0.001

    assert abs(
        record.discharged_mah - 12518.0
    ) < 0.001

    assert abs(
        record.remaining - 0.96
    ) < 0.001

    assert abs(
        record.temperature_c - 26.5
    ) < 0.001

    assert record.cell_count == 4

    assert record.cell_voltages_v == [
        4.01,
        4.02,
        4.01,
        4.01,
    ]

    assert abs(
        record.max_cell_voltage_delta_v - 0.01
    ) < 0.001


def test_mavlink_tlog_battery_raw_data_preserved():
    parser = MAVLinkTLogParser(FIXTURE)

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
