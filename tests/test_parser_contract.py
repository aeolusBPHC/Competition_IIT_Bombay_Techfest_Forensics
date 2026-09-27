from pathlib import Path

from platform_parsers.common.base_parser import BaseForensicParser
from platform_parsers.common.registry import ParserRegistry

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
        Path("tests/fixtures/synthetic_ardupilot_forensics.bin"),
    ),
    (
        ArduPilotTLogParser,
        Path("tests/fixtures/synthetic_ardupilot.tlog"),
    ),
    (
        BetaflightBlackboxParser,
        Path("tests/fixtures/synthetic_betaflight_blackbox.bbl"),
    ),
    (
        INAVBlackboxParser,
        Path("tests/fixtures/synthetic_inav_blackbox.bbl"),
    ),
    (
        MAVLinkTLogParser,
        Path("tests/fixtures/synthetic_mavlink_gps.tlog"),
    ),
]


REQUIRED_METHODS = [
    "identify",
    "get_metadata",
    "extract_gps",
    "extract_navigation",
    "extract_battery",
    "extract_telemetry",
    "extract_failsafe",
    "extract_commands",
    "extract_command_acks",
    "extract_states",
    "extract_parameters",
    "extract_events",
    "parse",
]


def test_all_registered_parsers_inherit_from_base_parser():
    registry = ParserRegistry()

    for parser_class in registry.parser_classes:
        assert issubclass(
            parser_class,
            BaseForensicParser,
        )


def test_all_registered_parsers_have_required_class_attributes():
    registry = ParserRegistry()

    for parser_class in registry.parser_classes:
        assert hasattr(parser_class, "platform_name")
        assert isinstance(parser_class.platform_name, str)
        assert parser_class.platform_name

        assert hasattr(parser_class, "supported_formats")
        assert isinstance(parser_class.supported_formats, (list, tuple, set))
        assert len(parser_class.supported_formats) > 0


def test_all_registered_parsers_have_required_methods():
    registry = ParserRegistry()

    for parser_class in registry.parser_classes:
        for method_name in REQUIRED_METHODS:
            assert hasattr(parser_class, method_name), (
                f"{parser_class.__name__} is missing "
                f"required method: {method_name}"
            )

            method = getattr(parser_class, method_name)
            assert callable(method), (
                f"{parser_class.__name__}.{method_name} "
                "must be callable"
            )


def test_all_registered_parsers_can_be_instantiated():
    for parser_class, evidence_path in PARSER_FIXTURES:
        parser = parser_class(evidence_path)

        assert isinstance(
            parser,
            BaseForensicParser,
        )


def test_all_registered_parsers_return_identification_result():
    for parser_class, evidence_path in PARSER_FIXTURES:
        result = parser_class.identify(evidence_path)

        assert isinstance(result, dict)

        assert "supported" in result
        assert "platform" in result
        assert "format" in result
        assert "confidence" in result


def test_all_supported_fixtures_parse_to_normalized_evidence():
    for parser_class, evidence_path in PARSER_FIXTURES:
        parser = parser_class(evidence_path)
        evidence = parser.parse()

        assert evidence is not None

        assert hasattr(evidence, "metadata")
        assert hasattr(evidence, "gps")
        assert hasattr(evidence, "navigation")
        assert hasattr(evidence, "battery")
        assert hasattr(evidence, "telemetry")
        assert hasattr(evidence, "failsafe")
        assert hasattr(evidence, "commands")
        assert hasattr(evidence, "command_acks")
        assert hasattr(evidence, "states")
        assert hasattr(evidence, "parameters")
        assert hasattr(evidence, "events")


def test_parser_platform_matches_normalized_metadata():
    for parser_class, evidence_path in PARSER_FIXTURES:
        parser = parser_class(evidence_path)
        evidence = parser.parse()

        assert evidence.metadata.platform == parser_class.platform_name


def test_registry_returns_parser_for_every_supported_fixture():
    registry = ParserRegistry()

    for parser_class, evidence_path in PARSER_FIXTURES:
        selected_parser = registry.get_parser(evidence_path)

        assert isinstance(
            selected_parser,
            parser_class,
        )
