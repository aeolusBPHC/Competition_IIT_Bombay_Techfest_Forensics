from pathlib import Path

from platform_parsers.px4.ulog_parser import PX4ULogParser
from platform_parsers.ardupilot.dataflash_parser import (
    ArduPilotDataFlashParser,
)
from platform_parsers.ardupilot.tlog_parser import (
    ArduPilotTLogParser,
)
from platform_parsers.betaflight.blackbox_parser import (
    BetaflightBlackboxParser,
)
from platform_parsers.inav.blackbox_parser import (
    INAVBlackboxParser,
)
from platform_parsers.mavlink.tlog_parser import (
    MAVLinkTLogParser,
)

from analysis.normalized_analysis import (
    NormalizedForensicAnalyzer,
)


PX4_EVIDENCE = Path(
    "repository/cases/CASE-001/"
    "EVD-20260919-175126/evidence/17_02_27.ulg"
)

ARDUPILOT_DATAFLASH_EVIDENCE = Path(
    "tests/fixtures/synthetic_ardupilot_forensics.bin"
)

ARDUPILOT_TLOG_EVIDENCE = Path(
    "tests/fixtures/synthetic_ardupilot.tlog"
)

MAVLINK_TLOG_EVIDENCE = Path(
    "tests/fixtures/synthetic_mavlink_gps.tlog"
)

BETAFLIGHT_EVIDENCE = Path(
    "tests/fixtures/synthetic_betaflight_blackbox.bbl"
)

INAV_EVIDENCE = Path(
    "tests/fixtures/synthetic_inav_blackbox.bbl"
)


def test_same_analyzer_accepts_all_supported_formats():
    evidence_sources = [
        (
            PX4ULogParser,
            PX4_EVIDENCE,
            "PX4",
        ),
        (
            ArduPilotDataFlashParser,
            ARDUPILOT_DATAFLASH_EVIDENCE,
            "ArduPilot",
        ),
        (
            ArduPilotTLogParser,
            ARDUPILOT_TLOG_EVIDENCE,
            "ArduPilot",
        ),
        (
            BetaflightBlackboxParser,
            BETAFLIGHT_EVIDENCE,
            "Betaflight",
        ),
        (
            INAVBlackboxParser,
            INAV_EVIDENCE,
            "INAV",
        ),
        (
            MAVLinkTLogParser,
            MAVLINK_TLOG_EVIDENCE,
            "MAVLink",
        ),
    ]

    for parser_class, evidence_path, expected_platform in evidence_sources:
        evidence = parser_class(evidence_path).parse()

        result = NormalizedForensicAnalyzer(
            evidence
        ).analyze()

        assert result["summary"]["platform"] == expected_platform
        assert result["summary"]["record_counts"]["gps"] > 0


def test_px4_normalized_analysis():
    evidence = PX4ULogParser(PX4_EVIDENCE).parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).analyze()

    assert result["summary"]["platform"] == "PX4"

    assert result["summary"]["record_counts"]["gps"] == 70755
    assert result["summary"]["record_counts"]["commands"] == 18
    assert result["summary"]["record_counts"]["command_acks"] == 21
    assert result["summary"]["record_counts"]["states"] == 4711


def test_ardupilot_dataflash_normalized_analysis():
    evidence = ArduPilotDataFlashParser(
        ARDUPILOT_DATAFLASH_EVIDENCE
    ).parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).analyze()

    assert result["summary"]["platform"] == "ArduPilot"

    assert result["summary"]["record_counts"]["gps"] == 2
    assert result["summary"]["record_counts"]["commands"] == 1
    assert result["summary"]["record_counts"]["states"] == 2


def test_ardupilot_tlog_normalized_analysis():
    evidence = ArduPilotTLogParser(
        ARDUPILOT_TLOG_EVIDENCE
    ).parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).analyze()

    assert result["summary"]["platform"] == "ArduPilot"

    assert result["summary"]["record_counts"]["gps"] == 2
    assert result["summary"]["record_counts"]["battery"] == 1


def test_generic_mavlink_tlog_normalized_analysis():
    evidence = MAVLinkTLogParser(
        MAVLINK_TLOG_EVIDENCE
    ).parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).analyze()

    assert result["summary"]["platform"] == "MAVLink"

    assert result["summary"]["record_counts"]["gps"] == 4
    assert result["summary"]["record_counts"]["battery"] == 2


def test_betaflight_normalized_analysis():
    evidence = BetaflightBlackboxParser(
        BETAFLIGHT_EVIDENCE
    ).parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).analyze()

    assert result["summary"]["platform"] == "Betaflight"

    assert result["summary"]["record_counts"]["gps"] == 2
    assert result["summary"]["record_counts"]["navigation"] == 2
    assert result["summary"]["record_counts"]["battery"] == 2


def test_inav_normalized_analysis():
    evidence = INAVBlackboxParser(
        INAV_EVIDENCE
    ).parse()

    result = NormalizedForensicAnalyzer(
        evidence
    ).analyze()

    assert result["summary"]["platform"] == "INAV"

    assert result["summary"]["record_counts"]["gps"] == 2
    assert result["summary"]["record_counts"]["navigation"] == 2
