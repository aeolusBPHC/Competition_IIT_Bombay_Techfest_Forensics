from __future__ import annotations

from typing import Any

from analysis.finding_model import ForensicFinding
from analysis.evidence_serialization import serialize_evidence

class FindingGenerator:
    """
    Converts normalized security indicators into structured
    forensic findings.

    This layer deliberately does not establish attack causality.
    It translates observed security indicators into evidence-backed
    forensic findings.
    """

    INDICATOR_TITLES = {
        "GPS_SPOOFING_STATE":
            "GPS spoofing state was reported",

        "GPS_JAMMING_STATE":
            "GPS jamming state was reported",

        "GPS_FIX_TYPE_CHANGE":
            "GPS fix type changed",

        "GPS_SATELLITE_COUNT_CHANGE":
            "GPS satellite count changed",

        "GPS_POSITION_DISCONTINUITY":
            "GPS position discontinuity detected",

        "NAVIGATION_POSITION_VALIDITY_CHANGE":
            "Navigation position validity changed",

        "COMMAND_WITHOUT_EXACT_ACK":
            "Command did not receive a matching acknowledgement",

        "ACK_WITHOUT_COMMAND":
            "Command acknowledgement has no matching command",

        "REPEATED_COMMAND_ID":
            "Command ID was repeated",

        "RX_MESSAGE_LOSS":
            "Telemetry message loss was reported",

        "RX_PARSE_ERRORS":
            "Telemetry parsing errors were reported",

        "RX_BUFFER_OVERRUN":
            "Telemetry receive buffer overrun was reported",

        "TX_BUFFER_OVERRUN":
            "Telemetry transmit buffer overrun was reported",

        "NO_GPS_RECORDS":
            "No GPS records were available",

        "NO_STATE_RECORDS":
            "No flight-state records were available",

        "NO_COMMAND_RECORDS":
            "No command records were available",
    }

    def __init__(self, indicators: dict[str, Any]):
        self.indicators = indicators

    def generate(self) -> list[ForensicFinding]:
        """
        Generate findings from all security indicators.
        """

        findings: list[ForensicFinding] = []
        counter = 1

        for indicator in self._iter_indicators():
            finding = self._indicator_to_finding(
                indicator,
                counter,
            )

            if finding is not None:
                findings.append(finding)
                counter += 1

        return findings

    def _iter_indicators(self):
        """
        Iterate through all indicator groups while preserving
        their original order.
        """

        groups = (
            "navigation",
            "command_and_control",
            "flight_control",
            "telemetry",
            "evidence_quality",
        )

        for group_name in groups:
            group = self.indicators.get(group_name, [])

            if isinstance(group, list):
                for indicator in group:
                    if isinstance(indicator, dict):
                        yield indicator

    def _indicator_to_finding(
        self,
        indicator: dict[str, Any],
        sequence: int,
    ) -> ForensicFinding | None:

        indicator_type = indicator.get(
            "indicator_type",
            "UNKNOWN_INDICATOR",
        )

        severity = indicator.get(
            "severity",
            "INFO",
        )

        confidence = indicator.get(
            "confidence",
            "MEDIUM",
        )

        timestamp = indicator.get(
            "timestamp_seconds",
        )

        end_timestamp = indicator.get(
            "end_timestamp_seconds",
        )

        description = indicator.get(
            "description",
            "A security-relevant indicator was observed.",
        )

        evidence = serialize_evidence(
            indicator.get("evidence", {})
        )

        category = indicator.get(
            "category",
            "UNKNOWN",
        )

        title = self.INDICATOR_TITLES.get(
            indicator_type,
            self._default_title(indicator_type),
        )

        finding_description = self._build_description(
            indicator_type=indicator_type,
            description=description,
            evidence=evidence,
        )

        return ForensicFinding(
            finding_id=f"FINDING-{sequence:04d}",
            category=category,
            severity=severity,
            title=title,
            description=finding_description,
            timestamp=timestamp,
            end_timestamp=end_timestamp,
            confidence=confidence,
            evidence_refs=self._build_evidence_refs(evidence),
            evidence=evidence,
            indicators={
                "indicator_type": indicator_type,
                "indicator": indicator,
            },
            source_platform=self._platform(),
        )

    def _build_description(
        self,
        indicator_type: str,
        description: str,
        evidence: Any,
    ) -> str:
        """
        Produce a conservative forensic interpretation.

        The description explicitly distinguishes observed telemetry
        from causal conclusions.
        """

        base = description.strip()

        if indicator_type in {
            "GPS_SPOOFING_STATE",
            "GPS_JAMMING_STATE",
            "GPS_POSITION_DISCONTINUITY",
            "NAVIGATION_POSITION_VALIDITY_CHANGE",
        }:
            return (
                f"{base} This represents a recorded navigation "
                "integrity indicator. The available log evidence "
                "does not by itself establish the cause of the "
                "observed condition."
            )

        if indicator_type in {
            "COMMAND_WITHOUT_EXACT_ACK",
            "ACK_WITHOUT_COMMAND",
            "REPEATED_COMMAND_ID",
        }:
            return (
                f"{base} This represents a command-and-control "
                "anomaly in the recorded telemetry. The log "
                "evidence alone does not establish whether the "
                "condition resulted from communication loss, "
                "software behavior, operator activity, or an "
                "adversarial action."
            )

        if indicator_type.startswith("FAILSAFE_"):
            return (
                f"{base} This represents a flight-controller "
                "failsafe or integrity condition recorded in the "
                "evidence. The record establishes the observed "
                "state but does not by itself establish its cause."
            )

        if indicator_type in {
            "RX_MESSAGE_LOSS",
            "RX_PARSE_ERRORS",
            "RX_BUFFER_OVERRUN",
            "TX_BUFFER_OVERRUN",
        }:
            return (
                f"{base} This represents a telemetry-system "
                "integrity indicator recorded in the evidence. "
                "Additional evidence may be required to determine "
                "the underlying cause."
            )

        return base

    @staticmethod
    def _default_title(indicator_type: str) -> str:
        """
        Convert an unknown indicator identifier into a readable title.
        """

        return indicator_type.replace("_", " ").capitalize()

    @staticmethod
    def _build_evidence_refs(evidence: Any) -> list[str]:
        """
        Extract stable evidence references when available.
        """

        if not isinstance(evidence, dict):
            return []

        refs: list[str] = []

        for key in (
            "source",
            "dataset",
            "record",
            "record_id",
            "evidence_ref",
        ):
            value = evidence.get(key)

            if value is not None:
                refs.append(f"{key}:{value}")

        return refs

    def _platform(self) -> str | None:
        """
        Recover platform information from the indicator summary.
        """

        summary = self.indicators.get("summary", {})

        if isinstance(summary, dict):
            return summary.get("platform")

        return None
