from pathlib import Path

from platform_parsers.ardupilot.tlog_parser import ArduPilotTLogParser


CASE_002_TLOG = Path(
    "repository/cases/CASE-002/raw/ardupilot_live.tlog"
)


def test_case_002_real_tlog_exists():
    assert CASE_002_TLOG.exists()
    assert CASE_002_TLOG.stat().st_size > 0


def test_case_002_real_tlog_normalized_parse():
    parser = ArduPilotTLogParser(str(CASE_002_TLOG))

    evidence = parser.parse()

    assert evidence.metadata is not None

    assert len(evidence.gps) == 0
    assert len(evidence.navigation) == 0
    assert len(evidence.battery) == 0
    assert len(evidence.telemetry) == 0
    assert len(evidence.failsafe) == 0
    assert len(evidence.commands) == 0
    assert len(evidence.command_acks) == 0

    assert len(evidence.states) == 3
    assert len(evidence.parameters) == 0
    assert len(evidence.events) == 3


def test_case_002_real_tlog_state():
    parser = ArduPilotTLogParser(str(CASE_002_TLOG))

    states = parser.extract_states()

    assert len(states) == 3

    assert states[0].source_platform == "ArduPilot"
    assert states[0].armed is False
    assert states[0].flight_mode == "STABILIZE"
    assert states[0].failsafe is None
    assert states[0].raw["system_status"] == 3

    assert states[1].source_platform == "ArduPilot"
    assert states[1].armed is False
    assert states[1].flight_mode == "STABILIZE"
    assert states[1].failsafe is None
    assert states[1].raw["system_status"] == 4

    assert states[2].source_platform == "ArduPilot"
    assert states[2].armed is False
    assert states[2].flight_mode == "STABILIZE"
    assert states[2].failsafe is None
    assert states[2].raw["system_status"] == 3

    assert states[0].timestamp < states[1].timestamp
    assert states[1].timestamp < states[2].timestamp

def test_case_002_real_tlog_events():
    parser = ArduPilotTLogParser(str(CASE_002_TLOG))

    events = parser.extract_events()

    assert len(events) == 3

    descriptions = [event.description for event in events]

    assert "Calibrating barometer" in descriptions
    assert "barometer calibration complete" in descriptions
    assert "GROUND START" in descriptions


def test_case_002_identifies_as_ardupilot_tlog():
    result = ArduPilotTLogParser.identify(str(CASE_002_TLOG))

    assert result["supported"] is True
    assert result["platform"] == "ArduPilot"
    assert result["format"] == "TLOG"
