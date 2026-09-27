from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


def _valid_points(records, x_field: str, y_field: str):
    """
    Extract records where both requested fields are present.
    """
    points = []

    for record in records:
        x = getattr(record, x_field, None)
        y = getattr(record, y_field, None)

        if x is None or y is None:
            continue

        points.append((x, y))

    return points


def _save_figure(fig, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig.tight_layout()
    fig.savefig(
        output_path,
        dpi=150,
        bbox_inches="tight",
    )
    plt.close(fig)


def plot_trajectory(navigation_records, output_dir: Path):
    """
    Plot recorded latitude/longitude trajectory.

    Platform independent:
    consumes only NavigationRecord fields.
    """

    points = _valid_points(
        navigation_records,
        "longitude",
        "latitude",
    )

    if len(points) < 2:
        return None

    longitude = [point[0] for point in points]
    latitude = [point[1] for point in points]

    fig, ax = plt.subplots()

    ax.plot(
        longitude,
        latitude,
        linewidth=1.5,
    )

    ax.scatter(
        longitude[0],
        latitude[0],
        marker="o",
        label="Start",
    )

    ax.scatter(
        longitude[-1],
        latitude[-1],
        marker="x",
        label="End",
    )

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Recorded Flight Trajectory")
    ax.legend()

    output_path = output_dir / "trajectory.png"

    _save_figure(fig, output_path)

    return output_path


def plot_altitude(navigation_records, output_dir: Path):
    """
    Plot altitude against normalized evidence time.
    """

    points = _valid_points(
        navigation_records,
        "timestamp",
        "altitude_m",
    )

    if len(points) < 2:
        return None

    timestamps = [point[0] for point in points]
    altitude = [point[1] for point in points]

    t0 = timestamps[0]
    time_seconds = [
        timestamp - t0
        for timestamp in timestamps
    ]

    fig, ax = plt.subplots()

    ax.plot(
        time_seconds,
        altitude,
        linewidth=1.2,
    )

    ax.set_xlabel("Time since first navigation record (s)")
    ax.set_ylabel("Altitude (m)")
    ax.set_title("Altitude vs Time")

    output_path = output_dir / "altitude_vs_time.png"

    _save_figure(fig, output_path)

    return output_path


def plot_speed(gps_records, output_dir: Path):
    """
    Plot GPS-derived speed against normalized evidence time.

    Uses GPSRecord.speed_m_s rather than assuming
    speed is part of NavigationRecord.
    """

    points = _valid_points(
        gps_records,
        "timestamp",
        "speed_m_s",
    )

    if len(points) < 2:
        return None

    timestamps = [point[0] for point in points]
    speed = [point[1] for point in points]

    t0 = timestamps[0]
    time_seconds = [
        timestamp - t0
        for timestamp in timestamps
    ]

    fig, ax = plt.subplots()

    ax.plot(
        time_seconds,
        speed,
        linewidth=1.2,
    )

    ax.set_xlabel("Time since first GPS record (s)")
    ax.set_ylabel("Speed (m/s)")
    ax.set_title("Speed vs Time")

    output_path = output_dir / "speed_vs_time.png"

    _save_figure(fig, output_path)

    return output_path


def plot_battery_voltage(battery_records, output_dir: Path):
    points = _valid_points(
        battery_records,
        "timestamp",
        "voltage_v",
    )

    if len(points) < 2:
        return None

    timestamps = [point[0] for point in points]
    values = [point[1] for point in points]

    t0 = timestamps[0]
    time_seconds = [
        timestamp - t0
        for timestamp in timestamps
    ]

    fig, ax = plt.subplots()

    ax.plot(
        time_seconds,
        values,
        linewidth=1.2,
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Voltage (V)")
    ax.set_title("Battery Voltage vs Time")

    output_path = output_dir / "battery_voltage_vs_time.png"

    _save_figure(fig, output_path)

    return output_path


def plot_battery_current(battery_records, output_dir: Path):
    points = _valid_points(
        battery_records,
        "timestamp",
        "current_a",
    )

    if len(points) < 2:
        return None

    timestamps = [point[0] for point in points]
    values = [point[1] for point in points]

    t0 = timestamps[0]
    time_seconds = [
        timestamp - t0
        for timestamp in timestamps
    ]

    fig, ax = plt.subplots()

    ax.plot(
        time_seconds,
        values,
        linewidth=1.2,
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Current (A)")
    ax.set_title("Battery Current vs Time")

    output_path = output_dir / "battery_current_vs_time.png"

    _save_figure(fig, output_path)

    return output_path


def plot_battery_remaining(battery_records, output_dir: Path):
    points = _valid_points(
        battery_records,
        "timestamp",
        "remaining",
    )

    if len(points) < 2:
        return None

    timestamps = [point[0] for point in points]
    values = [point[1] for point in points]

    t0 = timestamps[0]
    time_seconds = [
        timestamp - t0
        for timestamp in timestamps
    ]

    fig, ax = plt.subplots()

    ax.plot(
        time_seconds,
        values,
        linewidth=1.2,
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Remaining")
    ax.set_title("Battery Remaining vs Time")

    output_path = output_dir / "battery_remaining_vs_time.png"

    _save_figure(fig, output_path)

    return output_path


def plot_battery_temperature(battery_records, output_dir: Path):
    points = _valid_points(
        battery_records,
        "timestamp",
        "temperature_c",
    )

    if len(points) < 2:
        return None

    timestamps = [point[0] for point in points]
    values = [point[1] for point in points]

    t0 = timestamps[0]
    time_seconds = [
        timestamp - t0
        for timestamp in timestamps
    ]

    fig, ax = plt.subplots()

    ax.plot(
        time_seconds,
        values,
        linewidth=1.2,
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title("Battery Temperature vs Time")

    output_path = output_dir / "battery_temperature_vs_time.png"

    _save_figure(fig, output_path)

    return output_path

def plot_battery_cell_delta(battery_records, output_dir: Path):
    points = _valid_points(
        battery_records,
        "timestamp",
        "max_cell_voltage_delta_v",
    )

    if len(points) < 2:
        return None

    timestamps = [point[0] for point in points]
    values = [point[1] for point in points]

    t0 = timestamps[0]
    time_seconds = [
        timestamp - t0
        for timestamp in timestamps
    ]

    fig, ax = plt.subplots()

    ax.plot(
        time_seconds,
        values,
        linewidth=1.2,
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Cell voltage delta (V)")
    ax.set_title("Battery Cell Voltage Imbalance vs Time")

    output_path = output_dir / "battery_cell_voltage_delta_vs_time.png"

    _save_figure(fig, output_path)

    return output_path


def plot_telemetry_rates(telemetry_records, output_dir: Path):
    tx_points = _valid_points(
        telemetry_records,
        "timestamp",
        "tx_rate_avg",
    )

    rx_points = _valid_points(
        telemetry_records,
        "timestamp",
        "rx_rate_avg",
    )

    if len(tx_points) < 2 and len(rx_points) < 2:
        return None

    fig, ax = plt.subplots()

    if len(tx_points) >= 2:
        timestamps = [point[0] for point in tx_points]
        values = [point[1] for point in tx_points]

        t0 = timestamps[0]

        time_seconds = [
            timestamp - t0
            for timestamp in timestamps
        ]

        ax.plot(
            time_seconds,
            values,
            label="TX rate",
            linewidth=1.2,
        )

    if len(rx_points) >= 2:
        timestamps = [point[0] for point in rx_points]
        values = [point[1] for point in rx_points]

        t0 = timestamps[0]

        time_seconds = [
            timestamp - t0
            for timestamp in timestamps
        ]

        ax.plot(
            time_seconds,
            values,
            label="RX rate",
            linewidth=1.2,
        )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Rate")
    ax.set_title("Telemetry TX/RX Rates")
    ax.legend()

    output_path = output_dir / "telemetry_rates_vs_time.png"

    _save_figure(fig, output_path)

    return output_path


def plot_telemetry_loss(telemetry_records, output_dir: Path):
    loss_points = _valid_points(
        telemetry_records,
        "timestamp",
        "rx_message_lost_count",
    )

    drop_points = _valid_points(
        telemetry_records,
        "timestamp",
        "rx_packet_drop_count",
    )

    error_points = _valid_points(
        telemetry_records,
        "timestamp",
        "rx_parse_errors",
    )

    if (
        len(loss_points) < 2
        and len(drop_points) < 2
        and len(error_points) < 2
    ):
        return None

    fig, ax = plt.subplots()

    if len(loss_points) >= 2:
        timestamps = [point[0] for point in loss_points]
        values = [point[1] for point in loss_points]
        t0 = timestamps[0]

        time_seconds = [
            timestamp - t0
            for timestamp in timestamps
        ]

        ax.plot(
            time_seconds,
            values,
            label="Messages lost",
            linewidth=1.2,
        )

    if len(drop_points) >= 2:
        timestamps = [point[0] for point in drop_points]
        values = [point[1] for point in drop_points]
        t0 = timestamps[0]

        time_seconds = [
            timestamp - t0
            for timestamp in timestamps
        ]

        ax.plot(
            time_seconds,
            values,
            label="Packets dropped",
            linewidth=1.2,
        )

    if len(error_points) >= 2:
        timestamps = [point[0] for point in error_points]
        values = [point[1] for point in error_points]
        t0 = timestamps[0]

        time_seconds = [
            timestamp - t0
            for timestamp in timestamps
        ]

        ax.plot(
            time_seconds,
            values,
            label="Parse errors",
            linewidth=1.2,
        )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Count")
    ax.set_title("Telemetry Loss, Drops and Parse Errors")
    ax.legend()

    output_path = output_dir / "telemetry_loss_vs_time.png"

    _save_figure(fig, output_path)

    return output_path

def plot_failsafe_timeline(failsafe_records, output_dir: Path):
    """
    Plot asserted normalized failsafe conditions.

    Each normalized failsafe field is represented as a separate
    horizontal band. No platform-specific interpretation is used.
    """

    fields = [
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

    active_fields = []

    for field_name in fields:
        has_true = any(
            getattr(record, field_name, None) is True
            for record in failsafe_records
        )

        if has_true:
            active_fields.append(field_name)

    if not active_fields:
        return None

    fig, ax = plt.subplots(
        figsize=(12, max(4, len(active_fields) * 0.45))
    )

    for row, field_name in enumerate(active_fields):
        timestamps = []
        values = []

        for record in failsafe_records:
            value = getattr(record, field_name, None)

            if value is None:
                continue

            timestamps.append(record.timestamp)
            values.append(1 if value else 0)

        if len(timestamps) < 1:
            continue

        t0 = timestamps[0]

        time_seconds = [
            timestamp - t0
            for timestamp in timestamps
        ]

        ax.step(
            time_seconds,
            [
                row + value * 0.8
                for value in values
            ],
            where="post",
        )

    ax.set_yticks(range(len(active_fields)))
    ax.set_yticklabels(active_fields)

    ax.set_xlabel("Time since first failsafe record (s)")
    ax.set_ylabel("Normalized failsafe condition")
    ax.set_title("Failsafe Condition Timeline")

    output_path = output_dir / "failsafe_timeline.png"

    _save_figure(fig, output_path)

    return output_path

def plot_state_timeline(state_records, output_dir: Path):
    """
    Plot normalized vehicle state transitions.
    """

    if not state_records:
        return None

    fig, ax = plt.subplots(
        figsize=(12, 6)
    )

    timestamps = [
        record.timestamp
        for record in state_records
        if record.timestamp is not None
    ]

    if len(timestamps) < 2:
        plt.close(fig)
        return None

    t0 = timestamps[0]

    time_seconds = [
        timestamp - t0
        for timestamp in timestamps
    ]

    armed = [
        1 if record.armed is True else 0
        for record in state_records
    ]

    failsafe = [
        1 if record.failsafe is True else 0
        for record in state_records
    ]

    gcs_lost = [
        1 if record.gcs_connection_lost is True else 0
        for record in state_records
    ]

    ax.step(
        time_seconds,
        armed,
        where="post",
        label="Armed",
    )

    ax.step(
        time_seconds,
        failsafe,
        where="post",
        label="Failsafe",
    )

    ax.step(
        time_seconds,
        gcs_lost,
        where="post",
        label="GCS connection lost",
    )

    ax.set_xlabel("Time since first state record (s)")
    ax.set_ylabel("State")
    ax.set_title("Normalized Vehicle State Timeline")

    ax.legend()

    output_path = output_dir / "state_timeline.png"

    _save_figure(fig, output_path)

    return output_path

def plot_command_ack_timeline(
    command_records,
    ack_records,
    output_dir: Path,
):
    """
    Plot normalized command and command-ACK records.

    Commands and ACKs are shown as separate event streams.
    No platform-specific command semantics are inferred.
    """

    if not command_records and not ack_records:
        return None

    fig, ax = plt.subplots(
        figsize=(12, 6)
    )

    command_points = []

    for record in command_records:
        if record.timestamp is None:
            continue

        command_points.append(
            (
                record.timestamp,
                record.command_id,
            )
        )

    ack_points = []

    for record in ack_records:
        if record.timestamp is None:
            continue

        ack_points.append(
            (
                record.timestamp,
                record.command_id,
            )
        )

    if not command_points and not ack_points:
        plt.close(fig)
        return None

    all_timestamps = [
        timestamp
        for timestamp, _ in command_points + ack_points
    ]

    t0 = min(all_timestamps)

    if command_points:
        command_x = [
            timestamp - t0
            for timestamp, _ in command_points
        ]

        command_y = [
            command_id
            for _, command_id in command_points
            if command_id is not None
        ]

        if command_y:
            command_x = [
                timestamp - t0
                for timestamp, command_id in command_points
                if command_id is not None
            ]

            ax.scatter(
                command_x,
                command_y,
                marker="o",
                label="Command",
            )

    if ack_points:
        ack_x = [
            timestamp - t0
            for timestamp, command_id in ack_points
            if command_id is not None
        ]

        ack_y = [
            command_id
            for _, command_id in ack_points
            if command_id is not None
        ]

        if ack_y:
            ax.scatter(
                ack_x,
                ack_y,
                marker="x",
                label="Command ACK",
            )

    ax.set_xlabel("Time since first command/ACK (s)")
    ax.set_ylabel("Command ID")
    ax.set_title("Command and ACK Timeline")
    ax.legend()

    output_path = output_dir / "command_ack_timeline.png"

    _save_figure(fig, output_path)

    return output_path

def plot_event_timeline(
    event_records,
    output_dir: Path,
):
    """
    Plot normalized forensic events over time.

    Event identifiers and descriptions are displayed as evidence.
    No platform-specific semantic interpretation is performed.
    """

    if not event_records:
        return None

    valid_records = [
        record
        for record in event_records
        if record.timestamp is not None
    ]

    if not valid_records:
        return None

    t0 = min(
        record.timestamp
        for record in valid_records
    )

    event_types = sorted(
        {
            record.event_type
            for record in valid_records
            if record.event_type is not None
        }
    )

    if not event_types:
        return None

    event_y = {
        event_type: index
        for index, event_type in enumerate(event_types)
    }

    fig, ax = plt.subplots(
        figsize=(12, max(4, len(event_types) * 0.6))
    )

    for record in valid_records:
        event_type = record.event_type

        if event_type not in event_y:
            continue

        ax.scatter(
            record.timestamp - t0,
            event_y[event_type],
            marker="o",
        )

    ax.set_yticks(
        range(len(event_types))
    )

    ax.set_yticklabels(event_types)

    ax.set_xlabel(
        "Time since first forensic event (s)"
    )

    ax.set_ylabel("Event type")
    ax.set_title("Normalized Forensic Event Timeline")

    output_path = output_dir / "event_timeline.png"

    _save_figure(fig, output_path)

    return output_path

def plot_security_indicator_timeline(
    indicators,
    output_dir: Path,
):
    """
    Plot normalized security indicators over time.

    Accepts either a list of indicator dictionaries or
    normalized indicator objects exposing equivalent attributes.

    The function uses the platform-independent normalized fields:
        timestamp_seconds
        end_timestamp_seconds
        indicator_type
        severity
    """

    if not indicators:
        return None

    def get_value(item, key):
        if isinstance(item, dict):
            return item.get(key)

        return getattr(item, key, None)

    records = []

    for indicator in indicators:
        timestamp = get_value(
            indicator,
            "timestamp_seconds",
        )

        if timestamp is None:
            continue

        indicator_type = get_value(
            indicator,
            "indicator_type",
        )

        if indicator_type is None:
            indicator_type = "UNKNOWN"

        severity = get_value(
            indicator,
            "severity",
        )

        end_timestamp = get_value(
            indicator,
            "end_timestamp_seconds",
        )

        records.append(
            (
                timestamp,
                end_timestamp,
                indicator_type,
                severity,
            )
        )

    if not records:
        return None

    t0 = min(
        timestamp
        for timestamp, _, _, _ in records
    )

    indicator_types = sorted(
        {
            indicator_type
            for _, _, indicator_type, _ in records
        }
    )

    y_positions = {
        indicator_type: index
        for index, indicator_type
        in enumerate(indicator_types)
    }

    fig, ax = plt.subplots(
        figsize=(
            12,
            max(5, len(indicator_types) * 0.5),
        )
    )

    for (
        timestamp,
        end_timestamp,
        indicator_type,
        severity,
    ) in records:

        y = y_positions[indicator_type]

        start_time = timestamp - t0

        if end_timestamp is not None:
            end_time = end_timestamp - t0

            if end_time > start_time:
                ax.plot(
                    [start_time, end_time],
                    [y, y],
                    linewidth=3,
                )

                ax.scatter(
                    start_time,
                    y,
                    marker="o",
                )

                ax.scatter(
                    end_time,
                    y,
                    marker="x",
                )

                continue

        ax.scatter(
            start_time,
            y,
            marker="o",
        )

    ax.set_yticks(
        range(len(indicator_types))
    )

    ax.set_yticklabels(
        indicator_types
    )

    ax.set_xlabel(
        "Time since first security indicator (s)"
    )

    ax.set_ylabel(
        "Indicator type"
    )

    ax.set_title(
        "Normalized Security Indicator Timeline"
    )

    output_path = (
        output_dir /
        "security_indicator_timeline.png"
    )

    _save_figure(
        fig,
        output_path,
    )

    return output_path



def generate_visualizations(
    evidence,
    output_dir: Path,
    security_indicators=None,
):
    """
    Generate all applicable platform-independent forensic visualizations.

    The plotting layer operates only on normalized evidence records.
    A visualization is generated only when the corresponding normalized
    data is available.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = {}
    unavailable = {}

    def run_plot(name, func, records):
        if not records:
            unavailable[name] = "No normalized evidence records available."
            return

        try:
            path = func(records, output_dir)

            if path is None:
                unavailable[name] = (
                    "Normalized records exist, but required fields "
                    "were unavailable."
                )
                return

            generated[name] = str(path)

        except Exception as exc:
            unavailable[name] = (
                f"Visualization generation failed: {exc}"
            )

    run_plot(
        "trajectory",
        plot_trajectory,
        evidence.navigation,
    )

    run_plot(
        "altitude",
        plot_altitude,
        evidence.navigation,
    )

    run_plot(
        "speed",
        plot_speed,
        evidence.gps,
    )

    run_plot(
        "battery_voltage",
        plot_battery_voltage,
        evidence.battery,
    )

    run_plot(
        "battery_current",
        plot_battery_current,
        evidence.battery,
    )

    run_plot(
        "battery_remaining",
        plot_battery_remaining,
        evidence.battery,
    )

    run_plot(
        "battery_temperature",
        plot_battery_temperature,
        evidence.battery,
    )

    run_plot(
        "battery_cell_delta",
        plot_battery_cell_delta,
        evidence.battery,
    )

    run_plot(
        "telemetry_rates",
        plot_telemetry_rates,
        evidence.telemetry,
    )

    run_plot(
        "telemetry_loss",
        plot_telemetry_loss,
        evidence.telemetry,
    )

    run_plot(
        "failsafe",
        plot_failsafe_timeline,
        evidence.failsafe,
    )

    run_plot(
        "state",
        plot_state_timeline,
        evidence.states,
    )

    if evidence.commands or evidence.command_acks:
        try:
            path = plot_command_ack_timeline(
                evidence.commands,
                evidence.command_acks,
                output_dir,
            )

            if path is not None:
                generated["command_ack"] = str(path)
            else:
                unavailable["command_ack"] = (
                    "Command/ACK records exist, but required "
                    "fields were unavailable."
                )

        except Exception as exc:
            unavailable["command_ack"] = (
                f"Visualization generation failed: {exc}"
            )
    else:
        unavailable["command_ack"] = (
            "No normalized command or ACK records available."
        )

    run_plot(
        "events",
        plot_event_timeline,
        evidence.events,
    )

    if security_indicators:
        try:
            path = plot_security_indicator_timeline(
                security_indicators,
                output_dir,
            )

            if path is not None:
                generated["security_indicators"] = str(path)
            else:
                unavailable["security_indicators"] = (
                    "Security indicators exist, but required "
                    "timestamps were unavailable."
                )

        except Exception as exc:
            unavailable["security_indicators"] = (
                f"Visualization generation failed: {exc}"
            )
    else:
        unavailable["security_indicators"] = (
            "No normalized security indicators available."
        )

    return {
        "generated": generated,
        "unavailable": unavailable,
        "output_dir": str(output_dir),
    }
