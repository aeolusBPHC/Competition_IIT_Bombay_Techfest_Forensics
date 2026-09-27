from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians
from typing import Any

import numpy as np

from platform_parsers.common.evidence_model import (
    GPSRecord,
    NavigationRecord,
    NormalizedEvidence,
)


@dataclass
class TrajectoryPoint:
    """Platform-independent metric trajectory observation."""

    timestamp: float

    x_m: float
    y_m: float
    z_m: float

    vx_m_s: float
    vy_m_s: float
    vz_m_s: float

    speed_m_s: float | None = None
    heading_deg: float | None = None

    horizontal_accuracy_m: float | None = None
    vertical_accuracy_m: float | None = None

    position_valid: bool = True


@dataclass
class TrajectoryDataset:
    """Numeric trajectory data suitable for ML."""

    timestamps: np.ndarray
    positions: np.ndarray
    velocities: np.ndarray
    features: np.ndarray
    feature_names: list[str]


def _finite(value: Any) -> float | None:
    """Return a finite float or None."""
    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(result):
        return None

    return result


def _extract_position_records(
    evidence: NormalizedEvidence,
) -> list[tuple[float, float, float, float]]:
    """
    Extract timestamped global positions.

    Navigation records are preferred because they are part of the
    normalized navigation schema. GPS records are used as fallback.
    """

    navigation = []

    for record in evidence.navigation:
        lat = _finite(record.latitude)
        lon = _finite(record.longitude)
        alt = _finite(record.altitude_m)

        if lat is None or lon is None or alt is None:
            continue

        if record.latitude_longitude_valid is False:
            continue

        navigation.append(
            (
                float(record.timestamp),
                lat,
                lon,
                alt,
            )
        )

    if navigation:
        navigation.sort(key=lambda item: item[0])
        return navigation

    gps = []

    for record in evidence.gps:
        lat = _finite(record.latitude)
        lon = _finite(record.longitude)
        alt = _finite(record.altitude_m)

        if lat is None or lon is None or alt is None:
            continue

        if record.fix_type is not None and record.fix_type <= 0:
            continue

        gps.append(
            (
                float(record.timestamp),
                lat,
                lon,
                alt,
            )
        )

    gps.sort(key=lambda item: item[0])
    return gps


def _latlon_to_local_metric(
    latitude: np.ndarray,
    longitude: np.ndarray,
    altitude: np.ndarray,
) -> np.ndarray:
    """
    Convert latitude/longitude/altitude to a local tangent-plane
    approximation in metres.

    x = east
    y = north
    z = relative altitude

    This is intended for local drone trajectories, not global
    geodesic surveying.
    """

    if len(latitude) == 0:
        return np.empty((0, 3), dtype=float)

    earth_radius_m = 6_378_137.0

    lat0 = radians(float(latitude[0]))
    lon0 = radians(float(longitude[0]))

    lat = np.radians(latitude)
    lon = np.radians(longitude)

    x = (
        earth_radius_m
        * (lon - lon0)
        * cos(lat0)
    )

    y = earth_radius_m * (lat - lat0)

    z = altitude - altitude[0]

    return np.column_stack((x, y, z))


def _derive_velocity(
    timestamps: np.ndarray,
    positions: np.ndarray,
) -> np.ndarray:
    """Derive velocity from metric position observations."""

    if len(positions) == 0:
        return np.empty((0, 3), dtype=float)

    if len(positions) == 1:
        return np.zeros((1, 3), dtype=float)

    velocity = np.zeros_like(positions, dtype=float)

    dt = np.diff(timestamps)

    valid = dt > 0

    velocity[1:][valid] = (
        positions[1:][valid] - positions[:-1][valid]
    ) / dt[valid, None]

    # Use the first valid derivative for the first sample.
    first_valid = np.flatnonzero(valid)

    if len(first_valid):
        velocity[0] = velocity[first_valid[0] + 1]

    # Invalid/repeated timestamps remain zero.
    velocity[~np.isfinite(velocity)] = 0.0

    return velocity


def _nearest_gps_attributes(
    evidence: NormalizedEvidence,
    timestamps: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Attach nearest normalized GPS speed and heading."""

    speeds = np.full(len(timestamps), np.nan, dtype=float)
    headings = np.full(len(timestamps), np.nan, dtype=float)

    records = []

    for record in evidence.gps:
        if record.speed_m_s is None and record.heading_deg is None:
            continue

        records.append(
            (
                float(record.timestamp),
                _finite(record.speed_m_s),
                _finite(record.heading_deg),
            )
        )

    if not records:
        return speeds, headings

    records.sort(key=lambda item: item[0])

    record_times = np.asarray(
        [item[0] for item in records],
        dtype=float,
    )

    for index, timestamp in enumerate(timestamps):
        nearest = int(
            np.argmin(np.abs(record_times - timestamp))
        )

        speed = records[nearest][1]
        heading = records[nearest][2]

        if speed is not None:
            speeds[index] = speed

        if heading is not None:
            headings[index] = heading

    return speeds, headings


def _build_from_native_trajectory(
    evidence: NormalizedEvidence,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """
    Build metric trajectory arrays from a parser-provided native source.

    The function is deliberately platform-independent: it knows only the
    normalized TrajectoryRecord contract, never PX4/ArduPilot/etc. topic
    names.
    """

    records = list(
        getattr(evidence, "trajectory", [])
    )

    if not records:
        raise ValueError(
            "No native normalized trajectory observations are available."
        )

    records.sort(
        key=lambda record: float(record.timestamp)
    )

    timestamps = []
    positions = []
    velocities = []
    accelerations = []
    position_valid = []
    velocity_valid = []

    previous_position_reset = None
    previous_vertical_reset = None

    segment_ids = []
    segment = 0

    for record in records:

        timestamp = _finite(record.timestamp)

        if timestamp is None:
            continue

        # A change in the vertical reset counter represents a new local
        # vertical reference. This is deliberately stricter than reacting
        # to velocity-reset changes, because velocity resets alone should
        # not split a physically continuous trajectory.
        vertical_reset = getattr(
            record,
            "vertical_reset_counter",
            None,
        )

        if (
            previous_vertical_reset is not None
            and vertical_reset is not None
            and vertical_reset != previous_vertical_reset
        ):
            segment += 1

        previous_vertical_reset = vertical_reset

        # A position-reset counter can change without an immediate
        # discontinuity. Keep the reset information in the normalized
        # record, but do not split solely on XY reset changes.
        previous_position_reset = getattr(
            record,
            "position_reset_counter",
            previous_position_reset,
        )

        x = _finite(record.x_m)
        y = _finite(record.y_m)
        z = _finite(record.z_m)

        vx = _finite(record.vx_m_s)
        vy = _finite(record.vy_m_s)
        vz = _finite(record.vz_m_s)

        ax = _finite(record.ax_m_s2)
        ay = _finite(record.ay_m_s2)
        az = _finite(record.az_m_s2)

        timestamps.append(timestamp)

        positions.append(
            [
                x if x is not None else np.nan,
                y if y is not None else np.nan,
                z if z is not None else np.nan,
            ]
        )

        velocities.append(
            [
                vx if vx is not None else np.nan,
                vy if vy is not None else np.nan,
                vz if vz is not None else np.nan,
            ]
        )

        accelerations.append(
            [
                ax if ax is not None else np.nan,
                ay if ay is not None else np.nan,
                az if az is not None else np.nan,
            ]
        )

        position_valid.append(
            bool(
                getattr(
                    record,
                    "position_valid",
                    False,
                )
            )
        )

        velocity_valid.append(
            bool(
                getattr(
                    record,
                    "velocity_valid",
                    False,
                )
            )
        )

        segment_ids.append(segment)

    timestamps = np.asarray(
        timestamps,
        dtype=float,
    )

    positions = np.asarray(
        positions,
        dtype=float,
    )

    velocities = np.asarray(
        velocities,
        dtype=float,
    )

    accelerations = np.asarray(
        accelerations,
        dtype=float,
    )

    position_valid = np.asarray(
        position_valid,
        dtype=bool,
    )

    velocity_valid = np.asarray(
        velocity_valid,
        dtype=bool,
    )

    segment_ids = np.asarray(
        segment_ids,
        dtype=int,
    )

    if len(timestamps) == 0:
        raise ValueError(
            "Native trajectory source contained no usable timestamps."
        )

    # For ML, a complete 3-D position is required. Invalid samples remain
    # represented in the forensic/native layer but are excluded from the
    # numeric training trajectory.
    usable = (
        position_valid
        & np.all(
            np.isfinite(positions),
            axis=1,
        )
    )

    timestamps = timestamps[usable]
    positions = positions[usable]
    velocities = velocities[usable]
    accelerations = accelerations[usable]
    velocity_valid = velocity_valid[usable]
    segment_ids = segment_ids[usable]

    # Native velocity is preferred. If a platform supplies a native
    # trajectory but not native velocity, derive it from positions.
    native_velocity_available = (
        np.all(
            np.isfinite(velocities),
            axis=1,
        )
        & velocity_valid
    )

    if not np.all(native_velocity_available):
        derived = _derive_velocity(
            timestamps,
            positions,
        )

        velocities = np.where(
            native_velocity_available[:, None],
            velocities,
            derived,
        )

    return (
        timestamps,
        positions,
        velocities,
        accelerations,
        segment_ids,
        position_valid[usable],
    )


def _build_from_global_navigation(
    evidence: NormalizedEvidence,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """
    Platform-independent fallback.

    Used when a parser does not expose a native metric trajectory.

    Position is derived from normalized latitude/longitude/altitude.
    Velocity is then derived numerically and explicitly represents a
    derived source rather than native state.
    """

    records = _extract_position_records(evidence)

    if not records:
        raise ValueError(
            "No valid normalized position observations were found."
        )

    timestamps = np.asarray(
        [item[0] for item in records],
        dtype=float,
    )

    latitude = np.asarray(
        [item[1] for item in records],
        dtype=float,
    )

    longitude = np.asarray(
        [item[2] for item in records],
        dtype=float,
    )

    altitude = np.asarray(
        [item[3] for item in records],
        dtype=float,
    )

    positions = _latlon_to_local_metric(
        latitude,
        longitude,
        altitude,
    )

    velocities = _derive_velocity(
        timestamps,
        positions,
    )

    accelerations = np.zeros_like(
        positions,
        dtype=float,
    )

    segment_ids = np.zeros(
        len(timestamps),
        dtype=int,
    )

    position_valid = np.ones(
        len(timestamps),
        dtype=bool,
    )

    return (
        timestamps,
        positions,
        velocities,
        accelerations,
        segment_ids,
        position_valid,
    )


def build_trajectory_dataset(
    evidence: NormalizedEvidence,
) -> TrajectoryDataset:
    """
    Convert NormalizedEvidence into a platform-independent trajectory
    dataset.

    Source selection:

    1. Parser-provided native normalized trajectory.
    2. Normalized navigation/GPS fallback.

    The ML layer never inspects platform names or native topic names.

    Feature columns:

        x_m
        y_m
        z_m
        vx_m_s
        vy_m_s
        vz_m_s
        speed_m_s
        heading_sin
        heading_cos
        position_valid
    """

    native = getattr(
        evidence,
        "trajectory",
        [],
    )

    if native:
        (
            timestamps,
            positions,
            velocities,
            accelerations,
            segment_ids,
            position_valid,
        ) = _build_from_native_trajectory(
            evidence
        )

        source = "native_or_normalized"
    else:
        (
            timestamps,
            positions,
            velocities,
            accelerations,
            segment_ids,
            position_valid,
        ) = _build_from_global_navigation(
            evidence
        )

        source = "derived"

    if len(timestamps) == 0:
        raise ValueError(
            "Trajectory construction produced no usable samples."
        )

    gps_speeds, gps_headings = (
        _nearest_gps_attributes(
            evidence,
            timestamps,
        )
    )

    speed = np.linalg.norm(
        velocities,
        axis=1,
    )

    # Prefer normalized GPS heading where available. Otherwise derive
    # heading from horizontal native/derived velocity.
    heading_rad = np.radians(
        gps_headings
    )

    velocity_heading = np.arctan2(
        velocities[:, 1],
        velocities[:, 0],
    )

    heading_rad = np.where(
        np.isfinite(heading_rad),
        heading_rad,
        velocity_heading,
    )

    # GPS speed is retained where present, but native/derived metric
    # velocity is the canonical trajectory speed.
    speed = np.where(
        np.isfinite(speed),
        speed,
        gps_speeds,
    )

    speed = np.nan_to_num(
        speed,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    heading_sin = np.sin(
        heading_rad
    )

    heading_cos = np.cos(
        heading_rad
    )

    heading_sin = np.nan_to_num(
        heading_sin,
        nan=0.0,
    )

    heading_cos = np.nan_to_num(
        heading_cos,
        nan=1.0,
    )

    # Position validity is represented numerically for compatibility
    # with the existing ML feature interface.
    position_valid_feature = (
        position_valid.astype(float)
    )

    features = np.column_stack(
        (
            positions,
            velocities,
            speed,
            heading_sin,
            heading_cos,
            position_valid_feature,
        )
    )

    feature_names = [
        "x_m",
        "y_m",
        "z_m",
        "vx_m_s",
        "vy_m_s",
        "vz_m_s",
        "speed_m_s",
        "heading_sin",
        "heading_cos",
        "position_valid",
    ]

    # Attach provenance/segment information without changing the existing
    # five-field public TrajectoryDataset constructor.
    dataset = TrajectoryDataset(
        timestamps=timestamps,
        positions=positions,
        velocities=velocities,
        features=features,
        feature_names=feature_names,
    )

    # These attributes are intentionally additive so existing trainer code
    # remains compatible.
    dataset.segment_ids = segment_ids
    dataset.accelerations = accelerations
    dataset.trajectory_source = source

    return dataset

