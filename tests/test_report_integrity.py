from pathlib import Path
import hashlib
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


def test_report_contains_integrity_section():
    evidence = ArduPilotDataFlashParser(
        FIXTURE
    ).parse()

    report = NormalizedForensicReport(
        evidence,
        evidence_hash="abc123",
        evidence_id="EVD-TEST-001",
        case_id="CASE-TEST",
    ).build()

    assert "integrity" in report

    assert report["integrity"]["hash_algorithm"] == (
        "SHA-256"
    )

    assert report["integrity"]["evidence_hash"] == (
        "abc123"
    )


def test_report_contains_case_and_evidence_identity():
    evidence = ArduPilotDataFlashParser(
        FIXTURE
    ).parse()

    report = NormalizedForensicReport(
        evidence,
        evidence_id="EVD-TEST-001",
        case_id="CASE-TEST",
    ).build()

    assert report["evidence"]["case_id"] == (
        "CASE-TEST"
    )

    assert report["evidence"]["evidence_id"] == (
        "EVD-TEST-001"
    )


def test_report_sha256_sidecar(tmp_path):
    evidence = ArduPilotDataFlashParser(
        FIXTURE
    ).parse()

    output = (
        tmp_path /
        "normalized_analysis.json"
    )

    report = NormalizedForensicReport(
        evidence
    )

    saved_path = report.save(output)

    hash_path = Path(
        str(saved_path) + ".sha256"
    )

    assert saved_path.exists()
    assert hash_path.exists()

    expected_hash = (
        hashlib.sha256(
            saved_path.read_bytes()
        ).hexdigest()
    )

    hash_contents = (
        hash_path.read_text(
            encoding="utf-8"
        ).strip()
    )

    recorded_hash = hash_contents.split()[0]

    assert recorded_hash == expected_hash


def test_report_hash_changes_when_report_changes(
    tmp_path
):
    evidence = ArduPilotDataFlashParser(
        FIXTURE
    ).parse()

    output = (
        tmp_path /
        "normalized_analysis.json"
    )

    report = NormalizedForensicReport(
        evidence
    )

    saved_path = report.save(output)

    hash_path = Path(
        str(saved_path) + ".sha256"
    )

    original_hash = (
        hash_path
        .read_text(
            encoding="utf-8"
        )
        .split()[0]
    )

    data = json.loads(
        saved_path.read_text(
            encoding="utf-8"
        )
    )

    data["analysis"]["tamper_test"] = True

    saved_path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    modified_hash = (
        hashlib.sha256(
            saved_path.read_bytes()
        ).hexdigest()
    )

    assert modified_hash != original_hash
