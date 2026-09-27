from pathlib import Path

from platform_parsers.ardupilot.dataflash_parser import (
    ArduPilotDataFlashParser,
)
from analysis.normalized_analysis import (
    NormalizedForensicAnalyzer,
)


FIXTURE = Path(
    "tests/fixtures/synthetic_ardupilot_forensics.bin"
)


def test_normalized_analysis_summary():
    evidence = ArduPilotDataFlashParser(FIXTURE).parse()

    analyzer = NormalizedForensicAnalyzer(evidence)
    result = analyzer.analyze()

    assert result["summary"]["platform"] == "ArduPilot"

    assert result["summary"]["record_counts"]["gps"] == 2
    assert result["summary"]["record_counts"]["commands"] == 1
    assert result["summary"]["record_counts"]["states"] == 2
    assert result["summary"]["record_counts"]["parameters"] == 1
    assert result["summary"]["record_counts"]["events"] == 2


def test_normalized_gps_analysis():
    evidence = ArduPilotDataFlashParser(FIXTURE).parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).gps_analysis()

    assert result["available"] is True
    assert result["sample_count"] == 2

    assert result["latitude"]["min"] == 47.397945
    assert result["latitude"]["max"] == 47.3979451

    assert result["longitude"]["min"] == 8.546176
    assert result["longitude"]["max"] == 8.5461761

    assert result["altitude_m"]["min"] == 230.0
    assert result["altitude_m"]["max"] == 231.0


def test_normalized_command_analysis():
    evidence = ArduPilotDataFlashParser(FIXTURE).parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).command_analysis()

    assert result["command_count"] == 1
    assert result["acknowledgement_count"] == 0

    assert result["command_id_counts"] == {
        400: 1
    }

    assert result["command_ids_with_ack"] == []
    assert result["command_ids_without_ack"] == [400]


def test_normalized_state_analysis():
    evidence = ArduPilotDataFlashParser(FIXTURE).parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).state_analysis()

    assert result["available"] is True
    assert result["state_count"] == 2

    assert result["flight_modes"] == {
        "4": 1
    }

    assert result["armed_states"] == {
        "1": 1
    }


def test_normalized_event_analysis():
    evidence = ArduPilotDataFlashParser(FIXTURE).parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).event_analysis()

    assert result["event_count"] == 2

    assert result["event_types"] == {
        "EV": 1,
        "ERR": 1,
    }
