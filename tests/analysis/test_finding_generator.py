from analysis.finding_generator import FindingGenerator


def test_finding_generator_creates_findings():
    indicators = {
        "summary": {
            "platform": "PX4",
        },
        "navigation": [
            {
                "category": "NAVIGATION",
                "indicator_type": "GPS_SPOOFING_STATE",
                "severity": "HIGH",
                "timestamp_seconds": 100.0,
                "end_timestamp_seconds": None,
                "confidence": "HIGH",
                "description": (
                    "GPS spoofing state was reported."
                ),
                "evidence": {
                    "dataset": "vehicle_gps_position",
                },
            }
        ],
        "command_and_control": [],
        "flight_control": [],
        "telemetry": [],
        "evidence_quality": [],
    }

    findings = FindingGenerator(indicators).generate()

    assert len(findings) == 1

    finding = findings[0]

    assert finding.finding_id == "FINDING-0001"
    assert finding.category == "NAVIGATION"
    assert finding.severity == "HIGH"
    assert finding.title == "GPS spoofing state was reported"
    assert finding.timestamp == 100.0
    assert finding.confidence == "HIGH"
    assert finding.source_platform == "PX4"


def test_finding_generator_preserves_multiple_indicators():
    indicators = {
        "summary": {
            "platform": "MAVLink",
        },
        "navigation": [
            {
                "category": "NAVIGATION",
                "indicator_type": "GPS_FIX_TYPE_CHANGE",
                "severity": "MEDIUM",
                "timestamp_seconds": 10.0,
                "confidence": "MEDIUM",
                "description": "GPS fix type changed.",
                "evidence": {},
            }
        ],
        "command_and_control": [
            {
                "category": "COMMAND_AND_CONTROL",
                "indicator_type": "COMMAND_WITHOUT_EXACT_ACK",
                "severity": "LOW",
                "timestamp_seconds": 20.0,
                "confidence": "MEDIUM",
                "description": "Command had no matching ACK.",
                "evidence": {},
            }
        ],
        "flight_control": [],
        "telemetry": [],
        "evidence_quality": [],
    }

    findings = FindingGenerator(indicators).generate()

    assert len(findings) == 2
    assert findings[0].finding_id == "FINDING-0001"
    assert findings[1].finding_id == "FINDING-0002"


def test_finding_generator_does_not_claim_causality():
    indicators = {
        "summary": {
            "platform": "PX4",
        },
        "navigation": [
            {
                "category": "NAVIGATION",
                "indicator_type": "GPS_POSITION_DISCONTINUITY",
                "severity": "MEDIUM",
                "timestamp_seconds": 50.0,
                "confidence": "MEDIUM",
                "description": (
                    "A large GPS position discontinuity was observed."
                ),
                "evidence": {},
            }
        ],
        "command_and_control": [],
        "flight_control": [],
        "telemetry": [],
        "evidence_quality": [],
    }

    findings = FindingGenerator(indicators).generate()

    assert len(findings) == 1

    description = findings[0].description.lower()

    assert "does not by itself establish the cause" in description
