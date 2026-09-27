from pathlib import Path

from analysis.ulog_inventory import inventory_ulog


FIXTURE = Path(
    "repository/cases/CASE-001/"
    "EVD-20260919-175126/evidence/17_02_27.ulg"
)


def test_ulog_inventory():
    inventory = inventory_ulog(FIXTURE)

    assert len(inventory) == 85

    names = {
        item["name"]
        for item in inventory
    }

    assert "vehicle_gps_position" in names
    assert "vehicle_global_position" in names
    assert "battery_status" in names
    assert "telemetry_status" in names
    assert "failsafe_flags" in names


def test_ulog_inventory_sample_counts():
    inventory = inventory_ulog(FIXTURE)

    by_name = {
        item["name"]: item
        for item in inventory
        if item["instance"] == 0
    }

    assert (
        by_name["vehicle_global_position"][
            "sample_count"
        ] == 252733
    )

    assert (
        by_name["battery_status"]["sample_count"]
        == 11814
    )

    assert (
        by_name["failsafe_flags"]["sample_count"]
        == 4465
    )
