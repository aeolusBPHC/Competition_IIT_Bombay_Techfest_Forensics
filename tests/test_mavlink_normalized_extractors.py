from platform_parsers.mavlink.normalized_extractors import (
    extract_failsafe,
)


class FakeMessage:
    def __init__(self, message_type, text):
        self._message_type = message_type
        self.text = text

    def get_type(self):
        return self._message_type

    def to_dict(self):
        return {
            "mavpackettype": self._message_type,
            "text": self.text,
        }


def make_record(text, timestamp=1.0):
    return {
        "timestamp": timestamp,
        "timestamp_us": int(timestamp * 1_000_000),
        "packet_offset": 0,
        "mavlink_version": 2,
        "message": FakeMessage(
            "STATUSTEXT",
            text,
        ),
    }


def test_failsafe_does_not_match_benign_status_text():
    records = [
        make_record("Radio calibrated"),
        make_record("GCS connected"),
        make_record("Battery voltage nominal"),
        make_record("EKF initialized"),
        make_record("Motor test complete"),
    ]

    result = extract_failsafe(
        records,
        "MAVLink",
    )

    assert result == []


def test_failsafe_matches_explicit_failsafe_messages():
    records = [
        make_record("Failsafe activated"),
        make_record("GCS failsafe"),
        make_record("Radio failsafe"),
        make_record("Geofence breach"),
        make_record("Battery failsafe"),
        make_record("Motor failure"),
        make_record("ESC arming failure"),
        make_record("EKF failure"),
    ]

    result = extract_failsafe(
        records,
        "MAVLink",
    )

    assert len(result) == 8

    assert result[0].critical_failure is True
    assert result[1].gcs_connection_lost is True
    assert result[2].gcs_connection_lost is True
    assert result[3].geofence_breached is True
    assert result[4].battery_warning == 1
    assert result[5].motor_failure is True
    assert result[6].esc_arming_failure is True
    assert result[7].navigator_failure is True
