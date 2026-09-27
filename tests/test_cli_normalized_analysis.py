import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "synthetic_ardupilot_forensics.bin"
)


def run_cli(*args):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.main",
            *args
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )


def test_normalized_analysis_cli_success(tmp_path):
    output = tmp_path / "normalized.json"

    result = run_cli(
        "normalized-analysis",
        "--input",
        str(FIXTURE),
        "--output",
        str(output)
    )

    assert result.returncode == 0
    assert output.exists()


def test_normalized_analysis_cli_platform_detection(tmp_path):
    output = tmp_path / "normalized.json"

    result = run_cli(
        "normalized-analysis",
        "--input",
        str(FIXTURE),
        "--output",
        str(output)
    )

    assert result.returncode == 0
    assert "[OK] Platform   : ArduPilot" in result.stdout
    assert "[OK] Format     : DataFlash" in result.stdout
    assert "[OK] Confidence : HIGH" in result.stdout


def test_normalized_analysis_cli_record_counts(tmp_path):
    output = tmp_path / "normalized.json"

    result = run_cli(
        "normalized-analysis",
        "--input",
        str(FIXTURE),
        "--output",
        str(output)
    )

    assert result.returncode == 0

    data = json.loads(
        output.read_text()
    )

    assert data["evidence"]["platform"] == "ArduPilot"
    assert data["evidence"]["format"] == "DataFlash"

    assert data["record_counts"] == {
        "gps": 2,
        "commands": 1,
        "command_acks": 0,
        "states": 2,
        "parameters": 1,
        "events": 2
    }


def test_normalized_analysis_cli_output_is_valid_json(tmp_path):
    output = tmp_path / "normalized.json"

    result = run_cli(
        "normalized-analysis",
        "--input",
        str(FIXTURE),
        "--output",
        str(output)
    )

    assert result.returncode == 0

    data = json.loads(
        output.read_text()
    )

    assert data["report_type"] == "normalized_forensic_analysis"
    assert data["report_version"] == "1.0"
    assert "analysis" in data
    assert "provenance" in data


def test_normalized_analysis_cli_missing_input(tmp_path):
    output = tmp_path / "normalized.json"

    result = run_cli(
        "normalized-analysis",
        "--input",
        str(tmp_path / "does_not_exist.bin"),
        "--output",
        str(output)
    )

    assert result.returncode != 0
    assert "[ERROR]" in result.stdout
    assert not output.exists()

def test_normalized_analysis_cli_contains_security_indicators(
    tmp_path
):
    output = tmp_path / "normalized.json"

    result = run_cli(
        "normalized-analysis",
        "--input",
        str(FIXTURE),
        "--output",
        str(output)
    )

    assert result.returncode == 0

    data = json.loads(
        output.read_text()
    )

    assert "security_indicators" in data

    indicators = data[
        "security_indicators"
    ]

    assert "summary" in indicators
    assert "navigation" in indicators
    assert "command_and_control" in indicators
    assert "flight_control" in indicators
    assert "telemetry" in indicators
    assert "evidence_quality" in indicators


def test_normalized_analysis_cli_contains_findings(
    tmp_path
):
    output = tmp_path / "normalized.json"

    result = run_cli(
        "normalized-analysis",
        "--input",
        str(FIXTURE),
        "--output",
        str(output)
    )

    assert result.returncode == 0

    data = json.loads(
        output.read_text()
    )

    assert "findings" in data
    assert isinstance(
        data["findings"],
        list
    )

    for finding in data["findings"]:
        assert "finding_id" in finding
        assert "category" in finding
        assert "severity" in finding
        assert "title" in finding
        assert "description" in finding
        assert "confidence" in finding

def test_normalized_analysis_calculates_evidence_hash(
    tmp_path,
):
    output = tmp_path / "normalized.json"

    result = run_cli(
        "normalized-analysis",
        "--input",
        str(FIXTURE),
        "--output",
        str(output),
    )

    assert result.returncode == 0

    data = json.loads(
        output.read_text()
    )

    integrity = data["integrity"]

    assert integrity["hash_algorithm"] == "SHA-256"

    assert integrity["evidence_hash"] is not None

    assert len(
        integrity["evidence_hash"]
    ) == 64

    assert (
        integrity["evidence_hash_source"]
        == "calculated_from_input"
    )

    assert (
        integrity["hash_verified"]
        is True
    )
