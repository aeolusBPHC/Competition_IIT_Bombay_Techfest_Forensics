from analysis.finding_model import ForensicFinding


def test_forensic_finding_to_dict():
    finding = ForensicFinding(
        finding_id="TEST-0001",
        category="GPS_ANOMALY",
        severity="HIGH",
        title="GPS anomaly detected",
        description="Test finding",
        timestamp=10.5,
        confidence="HIGH",
        indicators={
            "latitude_jump_m": 125.0,
        },
    )

    result = finding.to_dict()

    assert result["finding_id"] == "TEST-0001"
    assert result["category"] == "GPS_ANOMALY"
    assert result["severity"] == "HIGH"
    assert result["timestamp"] == 10.5
    assert result["indicators"]["latitude_jump_m"] == 125.0
