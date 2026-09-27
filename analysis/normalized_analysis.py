from collections import Counter
from typing import Any
import math

from platform_parsers.common.evidence_model import NormalizedEvidence
from analysis.normalized_timeline import NormalizedTimelineBuilder


class NormalizedForensicAnalyzer:
    """
    Platform-independent forensic analysis.

    This analyzer consumes NormalizedEvidence only.
    Platform-specific interpretation is performed by the
    parser layer before normalized analysis begins.
    """

    def __init__(self, evidence: NormalizedEvidence):
        self.evidence = evidence

    def summarize(self) -> dict[str, Any]:
        """Return a high-level summary of the normalized evidence."""

        return {
            "platform": self.evidence.metadata.platform,
            "format": self.evidence.metadata.format,
            "source_file": self.evidence.metadata.source_file,
            "record_counts": {
                "gps": len(self.evidence.gps),
                "navigation": len(self.evidence.navigation),
                "battery": len(self.evidence.battery),
                "telemetry": len(self.evidence.telemetry),
                "failsafe": len(self.evidence.failsafe),
                "commands": len(self.evidence.commands),
                "command_acks": len(self.evidence.command_acks),
                "states": len(self.evidence.states),
                "parameters": len(self.evidence.parameters),
                "events": len(self.evidence.events),
            },
        }

    def gps_analysis(self) -> dict[str, Any]:
        """Calculate platform-independent GPS statistics."""

        gps = self.evidence.gps

        if not gps:
            return {
                "available": False,
                "sample_count": 0,
            }

        latitudes = [
            record.latitude
            for record in gps
            if record.latitude is not None
        ]

        longitudes = [
            record.longitude
            for record in gps
            if record.longitude is not None
        ]

        altitudes = [
            record.altitude_m
            for record in gps
            if record.altitude_m is not None
        ]

        speeds = [
            record.speed_m_s
            for record in gps
            if record.speed_m_s is not None
        ]

        satellites = [
            record.satellites
            for record in gps
            if record.satellites is not None
        ]

        return {
            "available": True,
            "sample_count": len(gps),
            "latitude": self._range_statistics(latitudes),
            "longitude": self._range_statistics(longitudes),
            "altitude_m": self._range_statistics(altitudes),
            "speed_m_s": self._range_statistics(speeds),
            "satellites": self._range_statistics(satellites),
            "time_range": {
                "start": gps[0].timestamp,
                "end": gps[-1].timestamp,
            },
        }

    def navigation_analysis(self) -> dict[str, Any]:
        """Analyze normalized navigation records."""

        records = self.evidence.navigation

        if not records:
            return {
                "available": False,
                "record_count": 0,
            }

        latitudes = [
            record.latitude
            for record in records
            if record.latitude is not None
        ]

        longitudes = [
            record.longitude
            for record in records
            if record.longitude is not None
        ]

        altitudes = [
            record.altitude_m
            for record in records
            if record.altitude_m is not None
        ]

        h_acc = [
            record.horizontal_position_accuracy_m
            for record in records
            if record.horizontal_position_accuracy_m is not None
        ]

        v_acc = [
            record.vertical_position_accuracy_m
            for record in records
            if record.vertical_position_accuracy_m is not None
        ]

        return {
            "available": True,
            "record_count": len(records),
            "latitude": self._range_statistics(latitudes),
            "longitude": self._range_statistics(longitudes),
            "altitude_m": self._range_statistics(altitudes),
            "horizontal_position_accuracy_m": self._range_statistics(
                h_acc
            ),
            "vertical_position_accuracy_m": self._range_statistics(
                v_acc
            ),
            "validity": {
                "latitude_longitude_invalid_count": sum(
                    record.latitude_longitude_valid is False
                    for record in records
                ),
                "altitude_invalid_count": sum(
                    record.altitude_valid is False
                    for record in records
                ),
                "terrain_altitude_invalid_count": sum(
                    record.terrain_altitude_valid is False
                    for record in records
                ),
            },
            "dead_reckoning_count": sum(
                record.dead_reckoning is True
                for record in records
            ),
            "time_range": {
                "start": records[0].timestamp,
                "end": records[-1].timestamp,
            },
        }

    def battery_analysis(self) -> dict[str, Any]:
        """Analyze normalized battery records."""

        records = self.evidence.battery

        if not records:
            return {
                "available": False,
                "record_count": 0,
            }

        voltage = [
            record.voltage_v
            for record in records
            if record.voltage_v is not None
        ]

        current = [
            record.current_a
            for record in records
            if record.current_a is not None
        ]

        remaining = [
            record.remaining
            for record in records
            if record.remaining is not None
        ]

        temperature = [
            record.temperature_c
            for record in records
            if record.temperature_c is not None
        ]

        cell_delta = [
            record.max_cell_voltage_delta_v
            for record in records
            if record.max_cell_voltage_delta_v is not None
        ]

        return {
            "available": True,
            "record_count": len(records),
            "voltage_v": self._range_statistics(voltage),
            "current_a": self._range_statistics(current),
            "remaining": self._range_statistics(remaining),
            "temperature_c": self._range_statistics(temperature),
            "cell_voltage_delta_v": self._range_statistics(
                cell_delta
            ),
            "connection": {
                "connected_count": sum(
                    record.connected is True
                    for record in records
                ),
                "disconnected_count": sum(
                    record.connected is False
                    for record in records
                ),
            },
            "faults": {
                "nonzero_fault_count": sum(
                    record.faults not in (None, 0)
                    for record in records
                ),
                "warning_count": sum(
                    record.warning not in (None, 0)
                    for record in records
                ),
            },
            "time_range": {
                "start": records[0].timestamp,
                "end": records[-1].timestamp,
            },
        }

    def telemetry_analysis(self) -> dict[str, Any]:
        """Analyze normalized telemetry records."""

        records = self.evidence.telemetry

        if not records:
            return {
                "available": False,
                "record_count": 0,
            }

        tx_rate = [
            record.tx_rate_avg
            for record in records
            if record.tx_rate_avg is not None
        ]

        rx_rate = [
            record.rx_rate_avg
            for record in records
            if record.rx_rate_avg is not None
        ]

        lost = [
            record.rx_message_lost_count
            for record in records
            if record.rx_message_lost_count is not None
        ]

        parse_errors = [
            record.rx_parse_errors
            for record in records
            if record.rx_parse_errors is not None
        ]

        drops = [
            record.rx_packet_drop_count
            for record in records
            if record.rx_packet_drop_count is not None
        ]

        lost_rate = [
            record.rx_message_lost_rate
            for record in records
            if record.rx_message_lost_rate is not None
        ]

        return {
            "available": True,
            "record_count": len(records),
            "tx_rate_avg": self._range_statistics(tx_rate),
            "rx_rate_avg": self._range_statistics(rx_rate),
            "rx_message_lost_count": {
                **self._range_statistics(lost),
                "total": sum(lost) if lost else None,
            },
            "rx_parse_errors": {
                **self._range_statistics(parse_errors),
                "total": sum(parse_errors) if parse_errors else None,
            },
            "rx_packet_drop_count": {
                **self._range_statistics(drops),
                "total": sum(drops) if drops else None,
            },
            "rx_message_lost_rate": self._range_statistics(
                lost_rate
            ),
            "protocol": {
                "mavlink_v2_count": sum(
                    record.mavlink_v2 is True
                    for record in records
                ),
                "flow_control_count": sum(
                    record.flow_control is True
                    for record in records
                ),
                "forwarding_count": sum(
                    record.forwarding is True
                    for record in records
                ),
                "ftp_count": sum(
                    record.ftp is True
                    for record in records
                ),
            },
            "time_range": {
                "start": records[0].timestamp,
                "end": records[-1].timestamp,
            },
        }

    def failsafe_analysis(self) -> dict[str, Any]:
        """Analyze normalized failsafe and safety-state records."""

        records = self.evidence.failsafe

        if not records:
            return {
                "available": False,
                "record_count": 0,
            }

        boolean_fields = [
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

        observed_flags = {}

        for field in boolean_fields:
            asserted = sum(
                getattr(record, field) is True
                for record in records
            )

            observed_flags[field] = {
                "asserted_count": asserted,
                "observed": asserted > 0,
            }

        battery_warning_values = sorted(
            {
                record.battery_warning
                for record in records
                if record.battery_warning is not None
            }
        )

        return {
            "available": True,
            "record_count": len(records),
            "flags": observed_flags,
            "battery_warning_values": battery_warning_values,
            "time_range": {
                "start": records[0].timestamp,
                "end": records[-1].timestamp,
            },
        }

    def command_analysis(self) -> dict[str, Any]:
        """Analyze normalized commands and command acknowledgements."""

        commands = self.evidence.commands
        acknowledgements = self.evidence.command_acks

        command_ids = Counter(
            command.command_id
            for command in commands
            if command.command_id is not None
        )

        ack_ids = Counter(
            ack.command_id
            for ack in acknowledgements
            if ack.command_id is not None
        )

        matched_ids = set(command_ids) & set(ack_ids)

        return {
            "command_count": len(commands),
            "acknowledgement_count": len(acknowledgements),
            "command_id_counts": dict(command_ids),
            "acknowledgement_id_counts": dict(ack_ids),
            "command_ids_with_ack": sorted(matched_ids),
            "command_ids_without_ack": sorted(
                set(command_ids) - set(ack_ids)
            ),
            "ack_ids_without_command": sorted(
                set(ack_ids) - set(command_ids)
            ),
        }

    def state_analysis(self) -> dict[str, Any]:
        """Analyze normalized vehicle state records."""

        states = self.evidence.states

        if not states:
            return {
                "available": False,
                "state_count": 0,
            }

        flight_modes = Counter(
            state.flight_mode
            for state in states
            if state.flight_mode is not None
        )

        armed_values = Counter(
            state.armed
            for state in states
            if state.armed is not None
        )

        failsafe_values = Counter(
            state.failsafe
            for state in states
            if state.failsafe is not None
        )

        gcs_loss_values = Counter(
            state.gcs_connection_lost
            for state in states
            if state.gcs_connection_lost is not None
        )

        return {
            "available": True,
            "state_count": len(states),
            "flight_modes": self._counter_to_dict(flight_modes),
            "armed_states": self._counter_to_dict(armed_values),
            "failsafe_states": self._counter_to_dict(failsafe_values),
            "gcs_connection_states": self._counter_to_dict(
                gcs_loss_values
            ),
            "time_range": {
                "start": states[0].timestamp,
                "end": states[-1].timestamp,
            },
        }

    def parameter_analysis(self) -> dict[str, Any]:
        """Analyze normalized configuration parameter records."""

        parameters = self.evidence.parameters

        if not parameters:
            return {
                "available": False,
                "parameter_count": 0,
            }

        category_prefixes = (
            "BAT",
            "CBRK",
            "COM",
            "GF",
            "MAV",
            "MIS",
            "NAV",
            "RC",
            "SYS",
        )

        category_counts = Counter()

        for parameter in parameters:
            matched = False

            for prefix in category_prefixes:
                if parameter.name.startswith(prefix):
                    category_counts[prefix] += 1
                    matched = True
                    break

            if not matched:
                category_counts["OTHER"] += 1

        return {
            "available": True,
            "parameter_count": len(parameters),
            "unique_parameter_count": len(
                {parameter.name for parameter in parameters}
            ),
            "category_counts": self._counter_to_dict(
                category_counts
            ),
        }

    def event_analysis(self) -> dict[str, Any]:
        """Summarize normalized forensic events."""

        events = self.evidence.events

        event_types = Counter(
            event.event_type
            for event in events
            if event.event_type is not None
        )

        severity = Counter(
            event.severity
            for event in events
            if event.severity is not None
        )

        # Preserve source-native event metadata without assigning
        # platform-specific semantics in the normalized analysis layer.
        native_event_metadata = Counter()

        for event in events:
            if not isinstance(event.data, dict):
                continue

            for key, value in event.data.items():
                if value is None:
                    continue

                # Preserve scalar native metadata values as generic
                # source-native observations. Do not infer normalized
                # severity or meaning from platform-specific values.
                if isinstance(value, (str, int, float, bool)):
                    native_event_metadata[str(key)] += 1

        return {
            "event_count": len(events),
            "event_types": self._counter_to_dict(event_types),
            "severity_counts": self._counter_to_dict(severity),
            "native_event_metadata_counts": dict(native_event_metadata),
        }

    def timeline_analysis(self) -> dict[str, Any]:
        """
        Build a platform-independent forensic timeline.
        """

        builder = NormalizedTimelineBuilder(
            evidence=self.evidence
        )

        return builder.build()

    def analyze(self) -> dict[str, Any]:
        """
        Run all platform-independent analyses.
        """

        return {
            "summary": self.summarize(),
            "gps": self.gps_analysis(),
            "navigation": self.navigation_analysis(),
            "battery": self.battery_analysis(),
            "telemetry": self.telemetry_analysis(),
            "failsafe": self.failsafe_analysis(),
            "commands": self.command_analysis(),
            "states": self.state_analysis(),
            "parameters": self.parameter_analysis(),
            "events": self.event_analysis(),
            "timeline": self.timeline_analysis(),
        }

    @staticmethod
    def _range_statistics(values: list) -> dict[str, Any]:
        """
        Calculate range statistics while ignoring NaN and non-finite values.

        Raw forensic values are preserved in the normalized records.
        This filtering only prevents invalid numeric values from
        contaminating aggregate statistics.
        """

        valid_values = [
            value
            for value in values
            if value is not None
            and math.isfinite(float(value))
        ]

        if not valid_values:
            return {
                "count": 0,
                "min": None,
                "max": None,
                "average": None,
            }

        return {
            "count": len(valid_values),
            "min": min(valid_values),
            "max": max(valid_values),
            "average": sum(valid_values) / len(valid_values),
        }

    @staticmethod
    def _counter_to_dict(
        counter: Counter,
    ) -> dict[str, int]:
        return {
            str(key): value
            for key, value in counter.items()
        }


def analyze_normalized_evidence(
    evidence: NormalizedEvidence,
) -> dict[str, Any]:
    """Convenience function for analyzing normalized evidence."""

    return NormalizedForensicAnalyzer(evidence).analyze()