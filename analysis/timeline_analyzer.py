from collections import defaultdict

from platform_parsers.common.evidence_model import NormalizedEvidence

from .finding_model import ForensicFinding


class TimelineAnalyzer:
    """
    Performs generic forensic analysis of the normalized event timeline.
    """

    def __init__(self, evidence: NormalizedEvidence):
        self.evidence = evidence

    def analyze(self) -> list[ForensicFinding]:
        findings = []

        findings.extend(self._analyze_command_ack_relationships())
        findings.extend(self._analyze_gcs_connection_events())
        findings.extend(self._analyze_state_transitions())

        return findings

    def _analyze_command_ack_relationships(self):
        findings = []

        commands = self.evidence.commands
        acknowledgements = self.evidence.command_acks

        if not commands:
            return findings

        ack_by_command = defaultdict(list)

        for ack in acknowledgements:
            command_id = getattr(ack, "command_id", None)

            if command_id is not None:
                ack_by_command[command_id].append(ack)

        for index, command in enumerate(commands, start=1):
            command_id = getattr(command, "command_id", None)

            if command_id is None:
                continue

            matching_acks = ack_by_command.get(command_id, [])

            if not matching_acks:
                timestamp = getattr(command, "timestamp", None)

                findings.append(
                    ForensicFinding(
                        finding_id=f"CMD-ACK-{index:04d}",
                        category="COMMAND_ACK",
                        severity="MEDIUM",
                        title="Command has no matching acknowledgement",
                        description=(
                            f"Command {command_id} was observed without a "
                            "matching command acknowledgement."
                        ),
                        timestamp=timestamp,
                        confidence="MEDIUM",
                        indicators={
                            "command_id": command_id,
                            "ack_count": 0,
                        },
                    )
                )

        return findings

    def _analyze_gcs_connection_events(self):
        findings = []

        for index, event in enumerate(self.evidence.events, start=1):
            event_type = getattr(event, "event_type", None)

            if event_type != "GCS_CONNECTION_STATE_CHANGE":
                continue

            timestamp = getattr(event, "timestamp", None)

            raw = getattr(event, "raw", {}) or {}

            state = (
                raw.get("state")
                or raw.get("connected")
                or raw.get("gcs_connection_lost")
            )

            findings.append(
                ForensicFinding(
                    finding_id=f"GCS-EVENT-{index:04d}",
                    category="GCS_CONNECTION",
                    severity="INFO",
                    title="Ground-control connection state changed",
                    description=(
                        "A ground-control-station connection state "
                        "transition was observed in the evidence."
                    ),
                    timestamp=timestamp,
                    confidence="HIGH",
                    indicators={
                        "state": state,
                        "event_type": event_type,
                    },
                )
            )

        return findings

    def _analyze_state_transitions(self):
        findings = []

        previous_state = None

        for index, state in enumerate(self.evidence.states, start=1):
            current_state = getattr(state, "state", None)

            if current_state is None:
                current_state = getattr(state, "nav_state", None)

            timestamp = getattr(state, "timestamp", None)

            if (
                previous_state is not None
                and current_state != previous_state
            ):
                findings.append(
                    ForensicFinding(
                        finding_id=f"STATE-{index:04d}",
                        category="STATE_TRANSITION",
                        severity="INFO",
                        title="Vehicle state transition detected",
                        description=(
                            f"Vehicle state changed from "
                            f"{previous_state} to {current_state}."
                        ),
                        timestamp=timestamp,
                        confidence="HIGH",
                        indicators={
                            "previous_state": previous_state,
                            "current_state": current_state,
                        },
                    )
                )

            previous_state = current_state

        return findings
