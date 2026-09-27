from dataclasses import dataclass, field
from typing import Any


@dataclass
class ForensicFinding:
    """
    Represents a single forensic finding produced by an analysis module.

    A finding contains:
    - a human-readable interpretation
    - structured normalized evidence
    - indicator metadata
    - provenance information
    """

    finding_id: str
    category: str
    severity: str
    title: str
    description: str

    timestamp: float | None = None
    end_timestamp: float | None = None

    confidence: str = "MEDIUM"

    evidence_refs: list[str] = field(default_factory=list)

    # Structured evidence supporting the finding.
    #
    # This is intentionally platform-independent. The content should
    # originate from NormalizedEvidence rather than PX4/ArduPilot/
    # Betaflight/INAV-specific logic.
    evidence: dict[str, Any] = field(default_factory=dict)

    indicators: dict[str, Any] = field(default_factory=dict)

    source_platform: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "timestamp": self.timestamp,
            "end_timestamp": self.end_timestamp,
            "confidence": self.confidence,
            "evidence_refs": self.evidence_refs,
            "evidence": self.evidence,
            "indicators": self.indicators,
            "source_platform": self.source_platform,
        }
