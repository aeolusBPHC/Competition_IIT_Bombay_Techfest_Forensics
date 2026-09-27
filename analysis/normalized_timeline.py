from dataclasses import asdict
from typing import Any

from platform_parsers.common.evidence_model import (
    CommandAckRecord,
    CommandRecord,
    FailsafeRecord,
    ForensicEvent,
    NormalizedEvidence,
    StateRecord,
)


class NormalizedTimelineBuilder:
    """
    Platform-independent forensic timeline reconstruction.

    This class consumes NormalizedEvidence only.

    It does not assume that the evidence originated from PX4,
    ArduPilot, or any other specific flight-controller platform.
    """

    def __init__(
        self,
        evidence: NormalizedEvidence,
        command_ack_window_s: float = 5.0,
    ):
        self.evidence = evidence
        self.command_ack_window_s = command_ack_window_s

    def build_events(self) -> list[ForensicEvent]:
        """
        Build a chronological event stream from normalized evidence.

        Events represent observations reconstructed from recorded
        evidence. They do not independently establish causality
        or malicious activity.
        """

        events: list[ForensicEvent] = []

        events.extend(self._command_events())
        events.extend(self._ack_events())
        events.extend(self._state_events())
        events.extend(self._failsafe_events())

        events.sort(key=lambda event: event.timestamp)

        return events

    def build_correlations(
        self,
        events: list[ForensicEvent] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Build temporal correlations between normalized events.

        Correlations are analytical observations and should not be
        interpreted as proof of causality or malicious activity.
        """

        if events is None:
            events = self.build_events()

        correlations: list[dict[str, Any]] = []

        commands = [
            event
            for event in events
            if event.event_type == "VEHICLE_COMMAND"
        ]

        acknowledgements = [
            event
            for event in events
            if event.event_type == "COMMAND_ACK"
        ]

        for command in commands:
            command_id = command.data.get("command_id")

            if command_id is None:
                continue

            candidates = [
                ack
                for ack in acknowledgements
                if ack.data.get("command_id") == command_id
                and ack.timestamp >= command.timestamp
                and (
                    ack.timestamp - command.timestamp
                    <= self.command_ack_window_s
                )
            ]

            if candidates:
                ack = min(
                    candidates,
                    key=lambda item: item.timestamp,
                )

                correlations.append(
                    {
                        "correlation_type": "COMMAND_ACK_TEMPORAL_PROXIMITY",
                        "timestamp": ack.timestamp,
                        "command_timestamp": command.timestamp,
                        "ack_timestamp": ack.timestamp,
                        "delta_seconds": (
                            ack.timestamp - command.timestamp
                        ),
                        "command_id": command_id,
                        "ack_result": ack.data.get("result"),
                        "interpretation": (
                            "A command and acknowledgement with the "
                            "same command ID occurred within the "
                            "configured temporal window."
                        ),
                    }
                )

            else:
                correlations.append(
                    {
                        "correlation_type": "COMMAND_ACK_NOT_MATCHED_BY_NORMALIZED_ID",
                        "timestamp": command.timestamp,
                        "command_timestamp": command.timestamp,
                        "command_id": command_id,
                        "interpretation": (
                            "No command acknowledgement with the same normalized "
                            "command ID was observed within the configured temporal "
                            "window. This does not by itself establish command "
                            "failure or absence of a protocol-level response."
                            
                            
                        ),
                    }
                )

        correlations.sort(key=lambda item: item["timestamp"])

        return correlations

    def build(self) -> dict[str, Any]:
        """
        Build the complete normalized forensic timeline.
        """

        events = self.build_events()
        correlations = self.build_correlations(events)

        return {
            "platform": self.evidence.metadata.platform,
            "format": self.evidence.metadata.format,
            "event_count": len(events),
            "correlation_count": len(correlations),
            "timeline_start": (
                events[0].timestamp if events else None
            ),
            "timeline_end": (
                events[-1].timestamp if events else None
            ),
            "events": [
                self._event_to_dict(event)
                for event in events
            ],
            "correlations": correlations,
            "forensic_note": (
                "Events and correlations represent observations "
                "reconstructed from recorded normalized evidence. "
                "Event classification and temporal correlation do "
                "not by themselves establish causality or malicious "
                "activity."
            ),
        }

    def _command_events(self) -> list[ForensicEvent]:
        events = []

        for command in self.evidence.commands:
            events.append(
                ForensicEvent(
                    timestamp=command.timestamp,
                    event_type="VEHICLE_COMMAND",
                    description=(
                        f"Vehicle command observed: "
                        f"{command.command_id}"
                    ),
                    source_platform=(
                        command.source_platform
                        or self.evidence.metadata.platform
                    ),
                    severity="INFO",
                    data={
                        "command_id": command.command_id,
                        "source_system": command.source_system,
                        "source_component": command.source_component,
                        "target_system": command.target_system,
                        "target_component": command.target_component,
                        "parameters": command.parameters,
                    },
                    raw=command.raw,
                )
            )

        return events

    def _ack_events(self) -> list[ForensicEvent]:
        events = []

        for ack in self.evidence.command_acks:
            events.append(
                ForensicEvent(
                    timestamp=ack.timestamp,
                    event_type="COMMAND_ACK",
                    description=(
                        f"Command acknowledgement observed: "
                        f"{ack.command_id}"
                    ),
                    source_platform=(
                        ack.source_platform
                        or self.evidence.metadata.platform
                    ),
                    severity="INFO",
                    data={
                        "command_id": ack.command_id,
                        "result": ack.result,
                        "source_system": ack.source_system,
                        "source_component": ack.source_component,
                        "target_system": ack.target_system,
                        "target_component": ack.target_component,
                    },
                    raw=ack.raw,
                )
            )

        return events

    def _state_events(self) -> list[ForensicEvent]:
        """
        Generate events only when a state value changes.

        This avoids creating an event for every repeated state sample.
        """

        states = sorted(
            self.evidence.states,
            key=lambda state: state.timestamp,
        )

        if not states:
            return []

        events: list[ForensicEvent] = []

        previous: StateRecord | None = None

        tracked_fields = [
            "armed",
            "flight_mode",
            "failsafe",
            "gcs_connection_lost",
            "landed",
            "takeoff",
            "preflight_checks_pass",
        ]

        for state in states:
            if previous is None:
                previous = state
                continue

            changes = {}

            for field in tracked_fields:
                old_value = getattr(previous, field)
                new_value = getattr(state, field)

                if (
                    old_value is not None
                    and new_value is not None
                    and old_value != new_value
                ):
                    changes[field] = {
                        "previous": old_value,
                        "current": new_value,
                    }

            if changes:
                if "gcs_connection_lost" in changes:
                    gcs_change = changes["gcs_connection_lost"]

                    events.append(
                        ForensicEvent(
                            timestamp=state.timestamp,
                            event_type="GCS_CONNECTION_STATE_CHANGE",
                            description=(
                                "GCS connection state changed"
                            ),
                            source_platform=(
                                state.source_platform
                                or self.evidence.metadata.platform
                            ),
                            severity="WARNING"
                            if gcs_change["current"]
                            else "INFO",
                            data={
                                "previous": gcs_change["previous"],
                                "current": gcs_change["current"],
                            },
                            raw=state.raw,
                        )
                    )
                events.append(
                    ForensicEvent(
                        timestamp=state.timestamp,
                        event_type="STATE_CHANGE",
                        description="Vehicle state changed",
                        source_platform=(
                            state.source_platform
                            or self.evidence.metadata.platform
                        ),
                        severity="INFO",
                        data={
                            "changes": changes,
                        },
                        raw=state.raw,
                    )
                )

            previous = state

        return events

    def _failsafe_events(self) -> list[ForensicEvent]:
        """
        Generate events when a failsafe flag changes state.

        Repeated True samples are not emitted repeatedly.
        """

        records = sorted(
            self.evidence.failsafe,
            key=lambda record: record.timestamp,
        )

        if not records:
            return []

        tracked_fields = [
            "angular_velocity_invalid",
            "attitude_invalid",
            "local_altitude_invalid",
            "local_position_invalid",
            "local_velocity_invalid",
            "global_position_invalid",
            "auto_mission_missing",
            "offboard_control_signal_lost",
            "home_position_invalid",
            "manual_control_signal_lost",
            "gcs_connection_lost",
            "battery_low_remaining_time",
            "battery_unhealthy",
            "geofence_breached",
            "mission_failure",
            "wind_limit_exceeded",
            "flight_time_limit_exceeded",
            "position_accuracy_low",
            "navigator_failure",
            "critical_failure",
            "esc_arming_failure",
            "imbalanced_propeller",
            "motor_failure",
        ]

        events: list[ForensicEvent] = []

        previous_values: dict[str, bool | None] = {
            field: None
            for field in tracked_fields
        }

        for record in records:
            for field in tracked_fields:
                current = getattr(record, field)

                if current is None:
                    continue

                previous = previous_values[field]

                if previous is None:
                    previous_values[field] = current
                    continue

                if current == previous:
                    continue

                if current is True:
                    event_type = "FAILSAFE_ASSERTED"
                    severity = "WARNING"
                    description = (
                        f"Failsafe flag asserted: {field}"
                    )
                else:
                    event_type = "FAILSAFE_CLEARED"
                    severity = "INFO"
                    description = (
                        f"Failsafe flag cleared: {field}"
                    )

                events.append(
                    ForensicEvent(
                        timestamp=record.timestamp,
                        event_type=event_type,
                        description=description,
                        source_platform=(
                            record.source_platform
                            or self.evidence.metadata.platform
                        ),
                        severity=severity,
                        data={
                            "flag": field,
                            "previous": previous,
                            "current": current,
                        },
                        raw=record.raw,
                    )
                )

                previous_values[field] = current

        return events

    @staticmethod
    def _event_to_dict(
        event: ForensicEvent,
    ) -> dict[str, Any]:
        return asdict(event)


def build_normalized_timeline(
    evidence: NormalizedEvidence,
    command_ack_window_s: float = 5.0,
) -> dict[str, Any]:
    """
    Convenience function for normalized timeline reconstruction.
    """

    builder = NormalizedTimelineBuilder(
        evidence=evidence,
        command_ack_window_s=command_ack_window_s,
    )

    return builder.build()
