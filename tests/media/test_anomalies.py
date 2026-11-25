from media import anomalies


def test_non_monotonic_and_duplicate_timestamps_are_reported_in_source_order():
    findings = anomalies._timestamp_gaps([
        (3.0, {"frame": 0}), (2.0, {"frame": 1}), (2.0, {"frame": 2}),
    ], source="test_clock")

    assert [finding["type"] for finding in findings] == [
        "NON_MONOTONIC_TIMESTAMP", "DUPLICATE_TIMESTAMP",
    ]
    assert findings[0]["previous_s"] == 3.0
    assert findings[0]["current_s"] == 2.0
    assert findings[1]["confidence"] == "high"


def test_altitude_rate_review_requires_known_metre_units_and_same_clock():
    samples = [
        {"index": 0, "timestamp": {"value": 0, "basis": "utc"},
         "altitude": {"absolute_m": {"value": 10, "units": "m"}}},
        {"index": 1, "timestamp": {"value": 1, "basis": "utc"},
         "altitude": {"absolute_m": {"value": 100, "units": "m"}}},
        {"index": 2, "timestamp": {"value": 2, "basis": "utc"},
         "altitude": {"relative_m": {"value": 1000, "units": None}}},
    ]

    findings = anomalies._altitude_jumps(samples, threshold_m_s=60)

    assert len(findings) == 1
    assert findings[0]["type"] == "ALTITUDE_JUMP"
    assert findings[0]["implied_vertical_speed_m_s"] == 90
    assert findings[0]["confidence"] == "medium"
