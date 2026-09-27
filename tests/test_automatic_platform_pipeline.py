from pathlib import Path

from platform_parsers.common.registry import ParserRegistry
from analysis.normalized_analysis import NormalizedForensicAnalyzer


PX4_EVIDENCE = Path(
    "repository/cases/CASE-001/"
    "EVD-20260919-175126/evidence/17_02_27.ulg"
)

ARDUPILOT_EVIDENCE = Path(
    "tests/fixtures/synthetic_ardupilot_forensics.bin"
)

GENERIC_MAVLINK_TLOG = Path(
    "tests/fixtures/synthetic_mavlink_gps.tlog"
)

ARDUPILOT_TLOG = Path(
    "tests/fixtures/synthetic_ardupilot.tlog"
)

BETAFLIGHT_EVIDENCE = Path(
    "tests/fixtures/synthetic_betaflight_blackbox.bbl"
)

INAV_EVIDENCE = Path(
    "tests/fixtures/synthetic_inav_blackbox.bbl"
)

EMUFLIGHT_EVIDENCE = Path(
    "tests/fixtures/synthetic_emuflight.bbl"
)

def test_registry_detects_px4():
    registry = ParserRegistry()

    result = registry.detect(PX4_EVIDENCE)

    assert result["supported"] is True
    assert result["platform"] == "PX4"
    assert result["format"] == "ULog"
    assert result["confidence"] == "HIGH"


def test_registry_detects_ardupilot():
    registry = ParserRegistry()

    result = registry.detect(ARDUPILOT_EVIDENCE)

    assert result["supported"] is True
    assert result["platform"] == "ArduPilot"
    assert result["format"] == "DataFlash"
    assert result["confidence"] == "HIGH"

def test_registry_detects_generic_mavlink_tlog():
    registry = ParserRegistry()

    result = registry.detect(GENERIC_MAVLINK_TLOG)

    assert result["supported"] is True
    assert result["platform"] == "MAVLink"
    assert result["format"] == "TLOG"
    assert result["confidence"] == "LOW"


def test_registry_detects_ardupilot_tlog():
    registry = ParserRegistry()

    result = registry.detect(ARDUPILOT_TLOG)

    assert result["supported"] is True
    assert result["platform"] == "ArduPilot"
    assert result["format"] == "TLOG"
    assert result["confidence"] == "HIGH"

def test_registry_detects_betaflight_blackbox():
    registry = ParserRegistry()

    detection = registry.detect(BETAFLIGHT_EVIDENCE)

    assert detection["supported"] is True
    assert detection["platform"] == "Betaflight"
    assert detection["format"] == "BLACKBOX"
    assert detection["confidence"] == "HIGH"


def test_registry_detects_inav_blackbox():
    registry = ParserRegistry()

    detection = registry.detect(INAV_EVIDENCE)

    assert detection["supported"] is True
    assert detection["platform"] == "INAV"
    assert detection["format"] == "BLACKBOX"
    assert detection["confidence"] == "HIGH"

def test_registry_detects_emuflight_blackbox():
    registry = ParserRegistry()

    detection = registry.detect(EMUFLIGHT_EVIDENCE)

    assert detection["supported"] is True
    assert detection["platform"] == "EmuFlight"
    assert detection["format"] == "Blackbox"
    assert detection["confidence"] == "HIGH"


def test_registry_selects_px4_parser():
    registry = ParserRegistry()

    parser = registry.get_parser(PX4_EVIDENCE)

    assert type(parser).__name__ == "PX4ULogParser"


def test_registry_selects_ardupilot_parser():
    registry = ParserRegistry()

    parser = registry.get_parser(ARDUPILOT_EVIDENCE)

    assert type(parser).__name__ == "ArduPilotDataFlashParser"

def test_registry_selects_generic_mavlink_tlog_parser():
    registry = ParserRegistry()

    parser = registry.get_parser(GENERIC_MAVLINK_TLOG)

    assert type(parser).__name__ == "MAVLinkTLogParser"


def test_registry_selects_ardupilot_tlog_parser():
    registry = ParserRegistry()

    parser = registry.get_parser(ARDUPILOT_TLOG)

    assert type(parser).__name__ == "ArduPilotTLogParser"

def test_registry_selects_betaflight_parser():
    registry = ParserRegistry()

    parser_class = registry.get_parser_class(BETAFLIGHT_EVIDENCE)

    assert parser_class.__name__ == "BetaflightBlackboxParser"


def test_registry_selects_inav_parser():
    registry = ParserRegistry()

    parser_class = registry.get_parser_class(INAV_EVIDENCE)

    assert parser_class.__name__ == "INAVBlackboxParser"

def test_registry_selects_emuflight_parser():
    registry = ParserRegistry()

    parser_class = registry.get_parser_class(EMUFLIGHT_EVIDENCE)

    assert parser_class.__name__ == "EmuFlightBlackboxParser"


def test_registry_runs_px4_pipeline():
    registry = ParserRegistry()

    parser = registry.get_parser(PX4_EVIDENCE)

    evidence = parser.parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).analyze()

    assert result["summary"]["platform"] == "PX4"
    assert result["summary"]["record_counts"]["gps"] > 0


def test_registry_runs_ardupilot_pipeline():
    registry = ParserRegistry()

    parser = registry.get_parser(ARDUPILOT_EVIDENCE)

    evidence = parser.parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).analyze()

    assert result["summary"]["platform"] == "ArduPilot"
    assert result["summary"]["record_counts"]["gps"] == 2
def test_registry_runs_generic_mavlink_tlog_pipeline():
    registry = ParserRegistry()

    parser = registry.get_parser(GENERIC_MAVLINK_TLOG)

    evidence = parser.parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).analyze()

    assert result["summary"]["platform"] == "MAVLink"
    assert result["summary"]["record_counts"]["gps"] == 4
    assert result["summary"]["record_counts"]["battery"] == 2

def test_registry_runs_ardupilot_tlog_pipeline():
    registry = ParserRegistry()

    parser = registry.get_parser(ARDUPILOT_TLOG)

    evidence = parser.parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).analyze()

    assert result["summary"]["platform"] == "ArduPilot"
    assert result["summary"]["record_counts"]["gps"] == 2
    assert result["summary"]["record_counts"]["battery"] == 1

def test_registry_runs_betaflight_pipeline():
    registry = ParserRegistry()

    parser = registry.get_parser(BETAFLIGHT_EVIDENCE)
    evidence = parser.parse()

    result = NormalizedForensicAnalyzer(evidence).analyze()

    assert result["summary"]["platform"] == "Betaflight"
    assert result["summary"]["record_counts"]["gps"] == 2
    assert result["summary"]["record_counts"]["navigation"] == 2
    assert result["summary"]["record_counts"]["battery"] == 2


def test_registry_runs_inav_pipeline():
    registry = ParserRegistry()

    parser = registry.get_parser(INAV_EVIDENCE)
    evidence = parser.parse()

    result = NormalizedForensicAnalyzer(evidence).analyze()

    assert result["summary"]["platform"] == "INAV"
    assert result["summary"]["record_counts"]["gps"] == 2
    assert result["summary"]["record_counts"]["navigation"] == 2


def test_registry_runs_emuflight_pipeline():
    registry = ParserRegistry()

    parser = registry.get_parser(EMUFLIGHT_EVIDENCE)
    evidence = parser.parse()

    result = NormalizedForensicAnalyzer(evidence).analyze()

    assert result["summary"]["platform"] == "EmuFlight"
    assert result["summary"]["record_counts"]["gps"] > 0
    assert result["summary"]["record_counts"]["states"] > 0
    assert result["summary"]["record_counts"]["events"] > 0
