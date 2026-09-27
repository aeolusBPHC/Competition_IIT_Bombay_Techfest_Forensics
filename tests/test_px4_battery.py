from pathlib import Path

import pytest

from platform_parsers.px4.ulog_parser import PX4ULogParser


FIXTURE = Path(
    "repository/cases/CASE-001/"
    "EVD-20260919-175126/evidence/17_02_27.ulg"
)


def test_battery_record_count():
    parser = PX4ULogParser(FIXTURE)

    battery = parser.extract_battery()

    assert len(battery) == 11814


def test_battery_values():
    parser = PX4ULogParser(FIXTURE)

    battery = parser.extract_battery()

    first = battery[0]

    assert first.timestamp == pytest.approx(
        75.992
    )

    assert first.voltage_v == pytest.approx(
        16.2
    )

    assert first.current_a == pytest.approx(
        -1.0
    )

    assert first.current_average_a == pytest.approx(
        15.0
    )

    assert first.discharged_mah == pytest.approx(
        -0.2111111
    )

    assert first.remaining == pytest.approx(
        0.9889984
    )

    assert first.cell_count == 4

    assert first.connected is True

    assert first.faults == 0

    assert first.warning == 0

    assert first.source_platform == "PX4"


def test_battery_cell_voltages():
    parser = PX4ULogParser(FIXTURE)

    battery = parser.extract_battery()

    first = battery[0]

    assert len(first.cell_voltages_v) == 14

    assert first.cell_voltages_v[0] == pytest.approx(
        0.0
    )

    assert first.cell_voltages_v[13] == pytest.approx(
        0.0
    )


def test_battery_raw_values_preserved():
    parser = PX4ULogParser(FIXTURE)

    battery = parser.extract_battery()

    first = battery[0]

    assert first.raw["dataset"] == "battery_status"

    assert first.raw["timestamp"] == 75992000

    assert first.raw["voltage_v"] == pytest.approx(
        16.2
    )

    assert first.raw["current_a"] == pytest.approx(
        -1.0
    )

    assert first.raw["remaining"] == pytest.approx(
        0.9889984
    )

    assert first.raw["cell_count"] == 4

    assert first.raw["connected"] == 1

    assert first.raw["faults"] == 0

    assert first.raw["warning"] == 0
