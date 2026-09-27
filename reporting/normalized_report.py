import hashlib
import json
from pathlib import Path
from typing import Any

from platform_parsers.common.evidence_model import NormalizedEvidence
from analysis.normalized_analysis import NormalizedForensicAnalyzer
from analysis.normalized_security_indicators import (
    NormalizedSecurityIndicatorEngine,
)
from analysis.finding_generator import FindingGenerator


class NormalizedForensicReport:
    """
    Generates a machine-readable forensic report from NormalizedEvidence.

    Evidence integrity:
    - If an acquisition-time hash is supplied, it is preserved.
    - If no acquisition-time hash is supplied, the source evidence file
      is hashed directly before report generation.
    - The report records how the evidence hash was obtained.
    - The report can also be protected with its own SHA-256 sidecar hash.
    """

    REPORT_TYPE = "normalized_forensic_analysis"
    REPORT_VERSION = "1.0"
    HASH_ALGORITHM = "SHA-256"

    def __init__(
        self,
        evidence: NormalizedEvidence,
        evidence_hash: str | None = None,
        evidence_id: str | None = None,
        case_id: str | None = None,
        evidence_hash_source: str | None = None,
        verify_existing_hash: bool = False,
    ):
        self.evidence = evidence
        self.evidence_id = evidence_id
        self.case_id = case_id

        self.source_path = self._resolve_source_path()

        self.evidence_hash = evidence_hash
        self.evidence_hash_source = evidence_hash_source
        self.hash_verified = None

        # ------------------------------------------------------------
        # Evidence integrity
        # ------------------------------------------------------------
        #
        # Prefer an acquisition-time hash when one exists.
        #
        # Otherwise calculate the hash directly from the source file.
        #
        if self.evidence_hash:
            if self.evidence_hash_source is None:
                self.evidence_hash_source = (
                    "acquisition_metadata"
                )

            # A hash calculated directly from the supplied input
            # evidence is already verified against that input.
            if self.evidence_hash_source == "calculated_from_input":
                self.hash_verified = True

            elif verify_existing_hash and self.source_path:
                calculated_hash = self.calculate_sha256(
                    self.source_path
                )

                self.hash_verified = (
                    calculated_hash.lower()
                    == self.evidence_hash.lower()
                )

                if not self.hash_verified:
                    raise ValueError(
                        "Evidence hash mismatch.\n"
                        f"Expected: {self.evidence_hash}\n"
                        f"Actual  : {calculated_hash}\n"
                        f"Source  : {self.source_path}"
                    )

        else:
            if self.source_path and self.source_path.is_file():
                self.evidence_hash = self.calculate_sha256(
                    self.source_path
                )

                self.evidence_hash_source = (
                    "calculated_from_input"
                )

                self.hash_verified = True

            else:
                self.evidence_hash_source = (
                    "unavailable_source_file"
                )

        self.analyzer = NormalizedForensicAnalyzer(
            evidence
        )

    # ================================================================
    # SOURCE PATH
    # ================================================================

    def _resolve_source_path(self) -> Path | None:
        """
        Resolve the original evidence source recorded by the parser.
        """

        source_file = self.evidence.metadata.source_file

        if not source_file:
            return None

        path = Path(source_file).expanduser()

        if not path.is_absolute():
            path = Path.cwd() / path

        path = path.resolve()

        return path

    # ================================================================
    # HASHING
    # ================================================================

    @staticmethod
    def calculate_sha256(file_path: Path) -> str:
        """
        Calculate SHA-256 for a file.

        The file is read in 1 MiB chunks so large forensic evidence
        files can be hashed without loading the entire file into RAM.
        """

        sha256 = hashlib.sha256()

        with file_path.open("rb") as file:
            while True:
                chunk = file.read(1024 * 1024)

                if not chunk:
                    break

                sha256.update(chunk)

        return sha256.hexdigest()

    # ================================================================
    # BUILD REPORT
    # ================================================================

    def build(self) -> dict[str, Any]:
        """Build the complete normalized forensic report."""

        analysis = self.analyzer.analyze()

        # ------------------------------------------------------------
        # Security indicators
        # ------------------------------------------------------------

        indicator_engine = NormalizedSecurityIndicatorEngine(
            self.evidence
        )

        security_indicators = indicator_engine.analyze()

        # ------------------------------------------------------------
        # Findings
        # ------------------------------------------------------------

        finding_generator = FindingGenerator(
            security_indicators,
        )

        findings = finding_generator.generate()

        # ------------------------------------------------------------
        # Report
        # ------------------------------------------------------------

        return {
            "report_type": self.REPORT_TYPE,
            "report_version": self.REPORT_VERSION,

            "evidence": {
                "case_id": self.case_id,
                "evidence_id": self.evidence_id,

                "source_file": (
                    self.evidence.metadata.source_file
                ),

                "platform": (
                    self.evidence.metadata.platform
                ),

                "format": (
                    self.evidence.metadata.format
                ),

                "firmware": (
                    self.evidence.metadata.firmware
                ),

                "firmware_version": (
                    self.evidence.metadata.firmware_version
                ),

                "vehicle_type": (
                    self.evidence.metadata.vehicle_type
                ),

                "start_time": (
                    self.evidence.metadata.start_time
                ),

                "end_time": (
                    self.evidence.metadata.end_time
                ),

                "duration": (
                    self.evidence.metadata.duration
                ),

                "metadata": (
                    self.evidence.metadata.metadata
                ),
            },

            # --------------------------------------------------------
            # INTEGRITY
            # --------------------------------------------------------

            "integrity": {
                "hash_algorithm": self.HASH_ALGORITHM,

                "evidence_hash": (
                    self.evidence_hash
                ),

                "evidence_hash_source": (
                    self.evidence_hash_source
                ),

                "hash_verified": (
                    self.hash_verified
                ),
            },

            # --------------------------------------------------------
            # RECORD COUNTS
            # --------------------------------------------------------

            "record_counts": {
                "gps": len(self.evidence.gps),

                "commands": len(
                    self.evidence.commands
                ),

                "command_acks": len(
                    self.evidence.command_acks
                ),

                "states": len(
                    self.evidence.states
                ),

                "parameters": len(
                    self.evidence.parameters
                ),

                "events": len(
                    self.evidence.events
                ),
            },

            # --------------------------------------------------------
            # ANALYSIS
            # --------------------------------------------------------

            "analysis": analysis,

            # --------------------------------------------------------
            # SECURITY INDICATORS
            # --------------------------------------------------------

            "security_indicators": (
                security_indicators
            ),

            # --------------------------------------------------------
            # FINDINGS
            # --------------------------------------------------------

            "findings": [
                finding.to_dict()
                for finding in findings
            ],

            # --------------------------------------------------------
            # PROVENANCE
            # --------------------------------------------------------

            "provenance": {
                "platform": (
                    self.evidence.metadata.platform
                ),

                "format": (
                    self.evidence.metadata.format
                ),

                "normalized_records": {
                    "gps": [
                        {
                            "timestamp": record.timestamp,
                            "source_platform": (
                                record.source_platform
                            ),
                            "raw": record.raw,
                        }
                        for record in self.evidence.gps
                    ],

                    "navigation": [
                        {
                            "timestamp": record.timestamp,
                            "source_platform": (
                                record.source_platform
                            ),
                            "raw": record.raw,
                        }
                        for record in self.evidence.navigation
                    ],

                    "battery": [
                        {
                            "timestamp": record.timestamp,
                            "source_platform": (
                                record.source_platform
                            ),
                            "raw": record.raw,
                        }
                        for record in self.evidence.battery
                    ],

                    "telemetry": [
                        {
                            "timestamp": record.timestamp,
                            "source_platform": (
                                record.source_platform
                            ),
                            "raw": record.raw,
                        }
                        for record in self.evidence.telemetry
                    ],

                    "failsafe": [
                        {
                            "timestamp": record.timestamp,
                            "source_platform": (
                                record.source_platform
                            ),
                            "raw": record.raw,
                        }
                        for record in self.evidence.failsafe
                    ],

                    "commands": [
                        {
                            "timestamp": record.timestamp,
                            "source_platform": (
                                record.source_platform
                            ),
                            "raw": record.raw,
                        }
                        for record in self.evidence.commands
                    ],

                    "command_acks": [
                        {
                            "timestamp": record.timestamp,
                            "source_platform": (
                                record.source_platform
                            ),
                            "raw": record.raw,
                        }
                        for record in self.evidence.command_acks
                    ],

                    "states": [
                        {
                            "timestamp": record.timestamp,
                            "source_platform": (
                                record.source_platform
                            ),
                            "raw": record.raw,
                        }
                        for record in self.evidence.states
                    ],

                    "parameters": [
                        {
                            "timestamp": record.timestamp,
                            "source_platform": (
                                record.source_platform
                            ),
                            "raw": record.raw,
                        }
                        for record in self.evidence.parameters
                    ],

                    "events": [
                        {
                            "timestamp": record.timestamp,
                            "event_type": (
                                record.event_type
                            ),
                            "description": (
                                record.description
                            ),
                            "severity": (
                                record.severity
                            ),
                            "data": record.data,
                            "source_platform": (
                                record.source_platform
                            ),
                            "raw": record.raw,
                        }
                        for record in self.evidence.events
                    ],
                },
            },
        }

    # ================================================================
    # SAVE
    # ================================================================

    def save(
        self,
        output_path,
        write_hash=True,
    ) -> Path:
        """
        Build and save the report as JSON.

        The report itself receives a SHA-256 sidecar:

            report.json
            report.json.sha256
        """

        output_path = Path(output_path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        report = self.build()

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                report,
                file,
                indent=2,
                ensure_ascii=False,
                default=str,
            )

            file.write("\n")

        if write_hash:
            report_hash = self.calculate_sha256(
                output_path
            )

            hash_path = Path(
                str(output_path) + ".sha256"
            )

            with hash_path.open(
                "w",
                encoding="utf-8",
            ) as file:
                file.write(
                    f"{report_hash}  "
                    f"{output_path.name}\n"
                )

        return output_path
