from pathlib import Path
import json

from platform_parsers.ardupilot.dataflash_parser import (
    ArduPilotDataFlashParser,
)

from reporting.normalized_report import (
    NormalizedForensicReport,
)


FIXTURE = Path(
    "tests/fixtures/synthetic_ardupilot_forensics.bin"
)


def test_normalized_report_build():
    evidence = ArduPilotDataFlashParser(
        FIXTURE
    ).parse()

    report = NormalizedForensicReport(
        evidence
    ).build()

    assert report["report_type"] == (
        "normalized_forensic_analysis"
    )

    assert report["report_version"] == "1.0"

    assert report["evidence"]["platform"] == (
        "ArduPilot"
    )

    assert report["evidence"]["format"] == (
        "DataFlash"
    )

    assert report["record_counts"]["gps"] == 2
    assert report["record_counts"]["commands"] == 1
    assert report["record_counts"]["states"] == 2
    assert report["record_counts"]["parameters"] == 1
    assert report["record_counts"]["events"] == 2


def test_normalized_report_provenance():
    evidence = ArduPilotDataFlashParser(
        FIXTURE
    ).parse()

    report = NormalizedForensicReport(
        evidence
    ).build()

    provenance = report["provenance"]

    assert provenance["platform"] == "ArduPilot"
    assert provenance["format"] == "DataFlash"

    assert len(
        provenance["normalized_records"]["gps"]
    ) == 2

    assert len(
        provenance["normalized_records"]["commands"]
    ) == 1

    gps = provenance["normalized_records"]["gps"][0]

    assert gps["source_platform"] == "ArduPilot"

    assert gps["raw"]["Lat"] == 473979450


def test_normalized_report_save(tmp_path):
    evidence = ArduPilotDataFlashParser(
        FIXTURE
    ).parse()

    output = tmp_path / "normalized_analysis.json"

    report = NormalizedForensicReport(
        evidence
    )

    saved_path = report.save(output)

    assert saved_path.exists()

    with saved_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        loaded = json.load(file)

    assert loaded["report_type"] == (
        "normalized_forensic_analysis"
    )

    assert loaded["evidence"]["platform"] == (
        "ArduPilot"
    )

    assert loaded["record_counts"]["gps"] == 2

def test_normalized_report_contains_security_indicators():
    evidence = ArduPilotDataFlashParser(
        FIXTURE
    ).parse()

    report = NormalizedForensicReport(
        evidence
    ).build()

    assert "security_indicators" in report

    security_indicators = report[
        "security_indicators"
    ]

    assert "summary" in security_indicators
    assert "navigation" in security_indicators
    assert "command_and_control" in security_indicators
    assert "flight_control" in security_indicators
    assert "telemetry" in security_indicators
    assert "evidence_quality" in security_indicators


def test_normalized_report_contains_findings():
    evidence = ArduPilotDataFlashParser(
        FIXTURE
    ).parse()

    report = NormalizedForensicReport(
        evidence
    ).build()

    assert "findings" in report
    assert isinstance(
        report["findings"],
        list,
    )

    for finding in report["findings"]:
        assert "finding_id" in finding
        assert "category" in finding
        assert "severity" in finding
        assert "title" in finding
        assert "description" in finding
        assert "confidence" in finding
