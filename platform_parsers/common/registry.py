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

from platform_parsers.emuflight.blackbox_parser import (
    EmuFlightBlackboxParser,
)

from platform_parsers.inav.blackbox_parser import (
    INAVBlackboxParser,
)

from platform_parsers.mavlink.tlog_parser import (
    MAVLinkTLogParser,
)

from platform_parsers.common.platform_detector import PlatformDetector

def get_parser_classes():
    return [
        PX4ULogParser,
        ArduPilotDataFlashParser,
        ArduPilotTLogParser,
        BetaflightBlackboxParser,
        INAVBlackboxParser,
        EmuFlightBlackboxParser,
        MAVLinkTLogParser,
    ]


class ParserRegistry:
    """
    Central registry for all supported forensic parsers.

    The registry is responsible for:
    1. Registering parser classes.
    2. Detecting the platform/format.
    3. Selecting the appropriate parser.
    """

    def __init__(self):
        self.parser_classes = get_parser_classes()

        self.detector = PlatformDetector()

        for parser_class in self.parser_classes:
            self.detector.register(parser_class)

    def detect(self, evidence_path):
        """
        Detect the platform and evidence format.
        """

        return self.detector.best_match(evidence_path)

    def get_parser_class(self, evidence_path):
        """
        Return the parser class selected for the evidence.
        """

        detection = self.detect(evidence_path)

        if not detection.get("supported", False):
            raise ValueError(
                f"Unsupported evidence: {evidence_path}"
            )

        platform = detection["platform"]
        evidence_format = detection["format"]

        for parser_class in self.parser_classes:
            if (
                parser_class.platform_name == platform
                and evidence_format in parser_class.supported_formats
            ):
                return parser_class

        raise ValueError(
            "No registered parser matches detected evidence: "
            f"{platform}/{evidence_format}"
        )

    def get_parser(self, evidence_path):
        """
        Instantiate and return the appropriate parser.
        """

        evidence_path = Path(evidence_path)

        parser_class = self.get_parser_class(evidence_path)

        return parser_class(evidence_path)
