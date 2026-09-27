from typing import Iterable

from platform_parsers.common.evidence_model import (
    TelemetryRecord,
    FailsafeRecord,
    CommandRecord,
    CommandAckRecord,
    StateRecord,
    ParameterRecord,
    ForensicEvent,
)


def _message_dict(message):
    try:
        return message.to_dict()
    except Exception:
        return {}


def extract_commands(records: Iterable, source_platform: str):
    commands = []

    for record in records:
        message = record["message"]
        message_type = message.get_type()

        if message_type not in {
            "COMMAND_LONG",
            "COMMAND_INT",
        }:
            continue

        raw = _message_dict(message)

        parameters = {
            key: value
            for key, value in raw.items()
            if key.startswith("param")
        }

        if message_type == "COMMAND_INT":
            parameters.update({
                "frame": getattr(message, "frame", None),
                "x": getattr(message, "x", None),
                "y": getattr(message, "y", None),
                "z": getattr(message, "z", None),
                "current": getattr(message, "current", None),
                "autocontinue": getattr(
                    message,
                    "autocontinue",
                    None,
                ),
            })

        if message_type == "COMMAND_LONG":
            parameters["confirmation"] = getattr(
                message,
                "confirmation",
                None,
            )

        commands.append(
            CommandRecord(
                timestamp=record["timestamp"],
                command_id=getattr(
                    message,
                    "command",
                    None,
                ),
                source_system=getattr(
                    message,
                    "get_srcSystem",
                    lambda: None,
                )(),
                source_component=getattr(
                    message,
                    "get_srcComponent",
                    lambda: None,
                )(),
                target_system=getattr(
                    message,
                    "target_system",
                    None,
                ),
                target_component=getattr(
                    message,
                    "target_component",
                    None,
                ),
                parameters=parameters,
                source_platform=source_platform,
                raw={
                    "mavpackettype": message_type,
                    "mavlink_version": record[
                        "mavlink_version"
                    ],
                    "timestamp_us": record[
                        "timestamp_us"
                    ],
                    "packet_offset": record[
                        "packet_offset"
                    ],
                    "message": raw,
                },
            )
        )

    return commands


def extract_command_acks(records: Iterable, source_platform: str):
    acknowledgements = []

    for record in records:
        message = record["message"]

        if message.get_type() != "COMMAND_ACK":
            continue

        raw = _message_dict(message)

        acknowledgements.append(
            CommandAckRecord(
                timestamp=record["timestamp"],
                command_id=getattr(
                    message,
                    "command",
                    None,
                ),
                result=getattr(
                    message,
                    "result",
                    None,
                ),
                source_system=getattr(
                    message,
                    "get_srcSystem",
                    lambda: None,
                )(),
                source_component=getattr(
                    message,
                    "get_srcComponent",
                    lambda: None,
                )(),
                target_system=getattr(
                    message,
                    "target_system",
                    None,
                ),
                target_component=getattr(
                    message,
                    "target_component",
                    None,
                ),
                source_platform=source_platform,
                raw={
                    "mavpackettype": "COMMAND_ACK",
                    "mavlink_version": record[
                        "mavlink_version"
                    ],
                    "timestamp_us": record[
                        "timestamp_us"
                    ],
                    "packet_offset": record[
                        "packet_offset"
                    ],
                    "message": raw,
                },
            )
        )

    return acknowledgements


def extract_states(records: Iterable, source_platform: str):
    states = []

    try:
        from pymavlink import mavutil
    except ImportError:
        mavutil = None

    last_armed = None
    last_mode = None
    last_system_status = None

    for record in records:
        message = record["message"]
        message_type = message.get_type()

        if message_type == "HEARTBEAT":

            base_mode = getattr(
                message,
                "base_mode",
                None,
            )

            armed = None

            if base_mode is not None:
                if mavutil is not None:
                    armed = bool(
                        base_mode
                        & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                    )

            flight_mode = None

            if mavutil is not None:
                try:
                    flight_mode = (
                        mavutil.mode_string_v10(message)
                    )
                except Exception:
                    flight_mode = None

            if flight_mode is None:
                custom_mode = getattr(
                    message,
                    "custom_mode",
                    None,
                )

                if custom_mode is not None:
                    flight_mode = str(custom_mode)

            system_status = getattr(
                message,
                "system_status",
                None,
            )

            failsafe = None

            if mavutil is not None:
                critical_states = {
                    getattr(
                        mavutil.mavlink,
                        "MAV_STATE_CRITICAL",
                        5,
                    ),
                    getattr(
                        mavutil.mavlink,
                        "MAV_STATE_EMERGENCY",
                        6,
                    ),
                }

                if system_status in critical_states:
                    failsafe = True

            state_changed = (
                armed != last_armed
                or flight_mode != last_mode
                or system_status != last_system_status
            )

            if state_changed:
                states.append(
                    StateRecord(
                        timestamp=record["timestamp"],
                        armed=armed,
                        flight_mode=flight_mode,
                        failsafe=failsafe,
                        source_platform=source_platform,
                        raw={
                            "mavpackettype": "HEARTBEAT",
                            "system_status": system_status,
                            "base_mode": base_mode,
                            "custom_mode": getattr(
                                message,
                                "custom_mode",
                                None,
                            ),
                            "mavlink_version": record[
                                "mavlink_version"
                            ],
                            "timestamp_us": record[
                                "timestamp_us"
                            ],
                            "message": _message_dict(message),
                        },
                    )
                )

            last_armed = armed
            last_mode = flight_mode
            last_system_status = system_status

        elif message_type == "EXTENDED_SYS_STATE":

            landed_state = getattr(
                message,
                "landed_state",
                None,
            )

            landed = None
            takeoff = None

            if mavutil is not None:
                landed_enum = getattr(
                    mavutil.mavlink,
                    "MAV_LANDED_STATE_ON_GROUND",
                    1,
                )

                in_air_enum = getattr(
                    mavutil.mavlink,
                    "MAV_LANDED_STATE_IN_AIR",
                    2,
                )

                landed = landed_state == landed_enum
                takeoff = landed_state == in_air_enum

            states.append(
                StateRecord(
                    timestamp=record["timestamp"],
                    landed=landed,
                    takeoff=takeoff,
                    source_platform=source_platform,
                    raw={
                        "mavpackettype": (
                            "EXTENDED_SYS_STATE"
                        ),
                        "landed_state": landed_state,
                        "mavlink_version": record[
                            "mavlink_version"
                        ],
                        "timestamp_us": record[
                            "timestamp_us"
                        ],
                        "message": _message_dict(message),
                    },
                )
            )

    return states


def extract_parameters(records: Iterable, source_platform: str):
    parameters = []

    for record in records:
        message = record["message"]
        message_type = message.get_type()

        if message_type not in {
            "PARAM_VALUE",
            "PARAM_SET",
        }:
            continue

        raw = _message_dict(message)

        name = getattr(
            message,
            "param_id",
            None,
        )

        if isinstance(name, bytes):
            name = name.decode(
                "utf-8",
                errors="replace",
            )

        if name is None:
            continue

        parameters.append(
            ParameterRecord(
                timestamp=record["timestamp"],
                name=str(name).rstrip("\x00"),
                value=getattr(
                    message,
                    "param_value",
                    None,
                ),
                source_platform=source_platform,
                raw={
                    "mavpackettype": message_type,
                    "mavlink_version": record[
                        "mavlink_version"
                    ],
                    "timestamp_us": record[
                        "timestamp_us"
                    ],
                    "message": raw,
                },
            )
        )

    return parameters


def extract_telemetry(records: Iterable, source_platform: str):
    telemetry = []

    for record in records:
        message = record["message"]
        message_type = message.get_type()
        raw = _message_dict(message)

        if message_type == "RADIO_STATUS":

            telemetry.append(
                TelemetryRecord(
                    timestamp=record["timestamp"],
                    rx_message_lost_count=getattr(
                        message,
                        "rxerrors",
                        None,
                    ),
                    tx_buffer_overruns=getattr(
                        message,
                        "txbuf",
                        None,
                    ),
                    source_platform=source_platform,
                    raw={
                        "mavpackettype": message_type,
                        "mavlink_version": record[
                            "mavlink_version"
                        ],
                        "timestamp_us": record[
                            "timestamp_us"
                        ],
                        "message": raw,
                    },
                )
            )

        elif message_type == "SYS_STATUS":

            drop_rate = getattr(
                message,
                "drop_rate_comm",
                None,
            )

            if drop_rate is not None:
                drop_rate = drop_rate / 100.0

            telemetry.append(
                TelemetryRecord(
                    timestamp=record["timestamp"],
                    rx_message_lost_rate=drop_rate,
                    rx_message_lost_count=getattr(
                        message,
                        "errors_comm",
                        None,
                    ),
                    source_platform=source_platform,
                    raw={
                        "mavpackettype": message_type,
                        "mavlink_version": record[
                            "mavlink_version"
                        ],
                        "timestamp_us": record[
                            "timestamp_us"
                        ],
                        "message": raw,
                    },
                )
            )

    return telemetry


def extract_failsafe(records: Iterable, source_platform: str):
    """
    Extract explicitly indicated failsafe-related states.

    This does not perform anomaly detection.

    Only explicit failsafe/failure terminology is mapped to
    normalized failsafe fields. Benign mentions of components
    such as "radio", "battery", "GCS", or "EKF" are ignored.
    """

    failsafe_records = []

    patterns = [
        (
            "gcs_connection_lost",
            (
                "gcs failsafe",
                "gcs connection lost",
                "gcs link lost",
                "ground station failsafe",
                "radio failsafe",
                "radio link lost",
                "radio connection lost",
            ),
        ),
        (
            "geofence_breached",
            (
                "geofence breach",
                "geofence breached",
                "geofence failsafe",
            ),
        ),
        (
            "battery_warning",
            (
                "battery failsafe",
                "battery warning",
                "low battery failsafe",
                "battery low",
            ),
        ),
        (
            "motor_failure",
            (
                "motor failure",
                "motor failsafe",
            ),
        ),
        (
            "esc_arming_failure",
            (
                "esc arming failure",
                "esc failure",
                "esc failsafe",
            ),
        ),
        (
            "navigator_failure",
            (
                "ekf failure",
                "ekf failsafe",
                "navigator failure",
                "navigation failure",
            ),
        ),
        (
            "critical_failure",
            (
                "failsafe activated",
                "failsafe active",
                "critical failure",
            ),
        ),
    ]

    for record in records:
        message = record["message"]

        if message.get_type() != "STATUSTEXT":
            continue

        text = getattr(
            message,
            "text",
            "",
        )

        if isinstance(text, bytes):
            text = text.decode(
                "utf-8",
                errors="replace",
            )

        text = str(text).strip()
        lowered = text.lower()

        matched = None

        for field_name, phrases in patterns:
            if any(
                phrase in lowered
                for phrase in phrases
            ):
                matched = field_name
                break

        if matched is None:
            continue

        values = {}

        if matched == "gcs_connection_lost":
            values["gcs_connection_lost"] = True

        elif matched == "geofence_breached":
            values["geofence_breached"] = True

        elif matched == "battery_warning":
            values["battery_warning"] = 1

        elif matched == "motor_failure":
            values["motor_failure"] = True

        elif matched == "esc_arming_failure":
            values["esc_arming_failure"] = True

        elif matched == "navigator_failure":
            values["navigator_failure"] = True

        elif matched == "critical_failure":
            values["critical_failure"] = True

        failsafe_records.append(
            FailsafeRecord(
                timestamp=record["timestamp"],
                source_platform=source_platform,
                raw={
                    "mavpackettype": "STATUSTEXT",
                    "message": _message_dict(message),
                    "text": text,
                    "mavlink_version": record[
                        "mavlink_version"
                    ],
                    "timestamp_us": record[
                        "timestamp_us"
                    ],
                },
                **values,
            )
        )

    return failsafe_records

def extract_events(records: Iterable, source_platform: str):
    events = []

    for record in records:
        message = record["message"]
        message_type = message.get_type()

        if message_type != "STATUSTEXT":
            continue

        raw = _message_dict(message)

        text = getattr(
            message,
            "text",
            "",
        )

        if isinstance(text, bytes):
            text = text.decode(
                "utf-8",
                errors="replace",
            )

        text = str(text).strip()

        severity_value = getattr(
            message,
            "severity",
            None,
        )

        severity = None

        if severity_value is not None:
            severity = str(severity_value)

        events.append(
            ForensicEvent(
                timestamp=record["timestamp"],
                event_type="STATUSTEXT",
                description=text,
                source_platform=source_platform,
                severity=severity,
                data={
                    "severity": severity_value,
                },
                raw={
                    "mavpackettype": message_type,
                    "mavlink_version": record[
                        "mavlink_version"
                    ],
                    "timestamp_us": record[
                        "timestamp_us"
                    ],
                    "packet_offset": record[
                        "packet_offset"
                    ],
                    "message": raw,
                },
            )
        )

    return events
