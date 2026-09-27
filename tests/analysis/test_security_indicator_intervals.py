from platform_parsers.common.evidence_model import (
    EvidenceMetadata,
    FailsafeRecord,
    NormalizedEvidence,
    StateRecord,
)

from analysis.normalized_security_indicators import (
    NormalizedSecurityIndicatorEngine,
)


def make_evidence(failsafe=None, states=None):
    metadata = EvidenceMetadata(
        source_file="synthetic.ulg",
        platform="PX4",
        format="ULog",
    )

    return NormalizedEvidence(
        metadata=metadata,
        failsafe=failsafe or [],
        states=states or [],
    )


def test_repeated_failsafe_samples_become_one_interval():
    evidence = make_evidence(
        failsafe=[
            FailsafeRecord(
                timestamp=10.0,
                gcs_connection_lost=True,
                source_platform="PX4",
            ),
            FailsafeRecord(
                timestamp=11.0,
                gcs_connection_lost=True,
                source_platform="PX4",
            ),
            FailsafeRecord(
                timestamp=12.0,
                gcs_connection_lost=True,
                source_platform="PX4",
            ),
            FailsafeRecord(
                timestamp=13.0,
                gcs_connection_lost=False,
                source_platform="PX4",
            ),
        ]
    )

    result = NormalizedSecurityIndicatorEngine(
        evidence
    ).analyze()

    indicators = [
        item
        for item in result["flight_control"]
        if item["indicator_type"] == "GCS_CONNECTION_LOST"
    ]

    assert len(indicators) == 1

    indicator = indicators[0]

    assert indicator["timestamp_seconds"] == 10.0
    assert indicator["end_timestamp_seconds"] == 12.0
    assert indicator["evidence"]["sample_count"] == 3
    assert indicator["evidence"]["interval_end"] == 12.0


def test_active_failsafe_at_end_is_closed_at_last_observation():
    evidence = make_evidence(
        failsafe=[
            FailsafeRecord(
                timestamp=20.0,
                motor_failure=False,
                source_platform="PX4",
            ),
            FailsafeRecord(
                timestamp=21.0,
                motor_failure=True,
                source_platform="PX4",
            ),
            FailsafeRecord(
                timestamp=22.0,
                motor_failure=True,
                source_platform="PX4",
            ),
        ]
    )

    result = NormalizedSecurityIndicatorEngine(
        evidence
    ).analyze()

    indicators = [
        item
        for item in result["flight_control"]
        if item["indicator_type"] == "MOTOR_FAILURE"
    ]

    assert len(indicators) == 1

    indicator = indicators[0]

    assert indicator["timestamp_seconds"] == 21.0
    assert indicator["end_timestamp_seconds"] == 22.0
    assert indicator["evidence"]["sample_count"] == 2
    assert indicator["evidence"]["still_active_at_end"] is True


def test_state_changes_are_emitted_only_on_transitions():
    evidence = make_evidence(
        states=[
            StateRecord(
                timestamp=1.0,
                armed=False,
                source_platform="PX4",
            ),
            StateRecord(
                timestamp=2.0,
                armed=False,
                source_platform="PX4",
            ),
            StateRecord(
                timestamp=3.0,
                armed=True,
                source_platform="PX4",
            ),
            StateRecord(
                timestamp=4.0,
                armed=True,
                source_platform="PX4",
            ),
            StateRecord(
                timestamp=5.0,
                armed=False,
                source_platform="PX4",
            ),
        ]
    )

    result = NormalizedSecurityIndicatorEngine(
        evidence
    ).analyze()

    indicators = [
        item
        for item in result["flight_control"]
        if item["indicator_type"] == "ARMED_STATE_CHANGE"
    ]

    assert len(indicators) == 2

    assert indicators[0]["timestamp_seconds"] == 3.0
    assert indicators[1]["timestamp_seconds"] == 5.0


def test_no_flight_control_records_produces_no_indicators():
    evidence = make_evidence()

    result = NormalizedSecurityIndicatorEngine(
        evidence
    ).analyze()

    assert result["flight_control"] == []
