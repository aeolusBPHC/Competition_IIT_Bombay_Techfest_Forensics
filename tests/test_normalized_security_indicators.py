from pathlib import Path

from analysis.normalized_security_indicators import (
    NormalizedSecurityIndicatorEngine,
)
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


PARSER_FIXTURES = [
    (
        PX4ULogParser,
        Path(
            "repository/cases/CASE-001/"
            "EVD-20260919-175126/evidence/17_02_27.ulg"
        ),
    ),
    (
        ArduPilotDataFlashParser,
        Path(
            "tests/fixtures/"
            "synthetic_ardupilot_forensics.bin"
        ),
    ),
    (
        ArduPilotTLogParser,
        Path(
            "tests/fixtures/"
            "synthetic_ardupilot.tlog"
        ),
    ),
    (
        BetaflightBlackboxParser,
        Path(
            "tests/fixtures/"
            "synthetic_betaflight_blackbox.bbl"
        ),
    ),
    (
        INAVBlackboxParser,
        Path(
            "tests/fixtures/"
            "synthetic_inav_blackbox.bbl"
        ),
    ),
    (
        MAVLinkTLogParser,
        Path(
            "tests/fixtures/"
            "synthetic_mavlink_gps.tlog"
        ),
    ),
]


def test_normalized_security_engine_accepts_all_platforms():

    for parser_class, evidence_path in PARSER_FIXTURES:

        evidence = parser_class(
            evidence_path
        ).parse()

        engine = NormalizedSecurityIndicatorEngine(
            evidence
        )

        result = engine.analyze()

        assert isinstance(result, dict)

        assert "summary" in result
        assert "navigation" in result
        assert "command_and_control" in result
        assert "flight_control" in result
        assert "evidence_quality" in result


def test_normalized_security_engine_reports_platform():

    for parser_class, evidence_path in PARSER_FIXTURES:

        evidence = parser_class(
            evidence_path
        ).parse()

        result = (
            NormalizedSecurityIndicatorEngine(
                evidence
            )
            .analyze()
        )

        assert (
            result["summary"]["platform"]
            == parser_class.platform_name
        )


def test_normalized_security_engine_reports_px4_counts():

    evidence = PX4ULogParser(
        Path(
            "repository/cases/CASE-001/"
            "EVD-20260919-175126/evidence/17_02_27.ulg"
        )
    ).parse()

    result = NormalizedSecurityIndicatorEngine(
        evidence
    ).analyze()

    counts = result["summary"]["record_counts"]

    assert counts["gps"] == 70755
    assert counts["commands"] == 18
    assert counts["command_acks"] == 21
    assert counts["states"] == 4711
