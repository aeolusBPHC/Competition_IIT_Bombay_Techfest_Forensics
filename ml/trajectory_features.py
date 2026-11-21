from __future__ import annotations

from dataclasses import dataclass, replace
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


FEATURE_NAMES = [
    "x_m", "y_m", "z_m", "vx_m_s", "vy_m_s", "vz_m_s",
    "speed_m_s", "heading_sin", "heading_cos", "position_valid",
]
COORDINATE_FRAME = "ENU"
FEATURE_CONTRACT_VERSION = 2


@dataclass
class TrajectoryDataset:
    """Shared numeric contract. Heading is course CCW from east, in ENU.

    Ground truth is optional and never becomes a model input. Real log
    targets are estimator observations, not independently measured truth.
    """

    timestamps: np.ndarray
    positions: np.ndarray
    velocities: np.ndarray
    features: np.ndarray
    feature_names: list[str]
    segment_ids: np.ndarray | None = None
    accelerations: np.ndarray | None = None
    ground_truth_positions: np.ndarray | None = None
    trajectory_source: str = "unspecified"
    coordinate_frame: str = COORDINATE_FRAME
    coordinate_origin: dict | None = None
    source_platform: str = "unspecified"
    trajectory_id: str = ""
    split: str = ""
    scenario: str = "real_log"
    label_kind: str = "estimator_observation"

    def subset(self, indices: np.ndarray) -> TrajectoryDataset:
        values = {}
        for name in (
            "timestamps", "positions", "velocities", "features",
            "segment_ids", "accelerations", "ground_truth_positions",
        ):
            value = getattr(self, name)
            if value is not None:
                values[name] = np.asarray(value)[indices]
        return replace(self, **values)


def trajectory_features(positions, velocities, valid=None, course=None):
    """Build the same ten features for every data source."""
    if valid is None:
        valid = np.ones(len(positions))
    if course is None:
        course = np.arctan2(velocities[:, 1], velocities[:, 0])
    return np.column_stack((
        positions, velocities, np.linalg.norm(velocities, axis=1),
        np.sin(course), np.cos(course), np.asarray(valid, dtype=float),
    ))


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


def _position_records_with_segments(evidence):
    def collect(records, navigation):
        result, segment, previous_invalid = [], 0, False
        previous_resets = (None, None)
        for record in records:
            values = tuple(_finite(value) for value in
                           (record.timestamp, record.latitude, record.longitude, record.altitude_m))
            timestamp, latitude, longitude, altitude = values
            valid = all(value is not None for value in values)
            valid &= latitude is not None and -90 <= latitude <= 90
            valid &= longitude is not None and -180 <= longitude <= 180
            if navigation:
                valid &= record.latitude_longitude_valid is not False and record.altitude_valid is not False
                resets = (record.latitude_longitude_reset_counter, record.altitude_reset_counter)
            else:
                valid &= record.fix_type is None or record.fix_type >= 3
                resets = (None, None)
            changed = any(old is not None and new is not None and old != new
                          for old, new in zip(previous_resets, resets))
            if previous_invalid or changed:
                segment += 1
            previous_resets = tuple(new if new is not None else old
                                    for old, new in zip(previous_resets, resets))
            previous_invalid = not valid
            if valid:
                result.append((timestamp, latitude, longitude, altitude, segment))
        return result
    # Preserve source order so a reversed clock remains a visible boundary.
    return collect(evidence.navigation, True) or collect(evidence.gps, False)


def _extract_position_records(evidence):
    return [record[:4] for record in _position_records_with_segments(evidence)]


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


def _derive_velocity(timestamps, positions, segment_ids=None, max_gap_s=None):
    """Backward differences only, never across a gap or reset."""
    velocity = np.zeros_like(positions, dtype=float)
    if len(positions) < 2:
        return velocity
    dt = np.diff(timestamps)
    if max_gap_s is None:
        # Adapt to sparse sources using only timing observed so far. A
        # whole-flight median would let later sampling alter past features.
        cadence = np.minimum.accumulate(np.where(np.isfinite(dt) & (dt > 0), dt, np.inf))
        max_gap_s = np.maximum(0.25, 2.5 * cadence)
    valid = np.isfinite(dt) & (dt > 0) & (dt <= max_gap_s)
    if segment_ids is not None:
        valid &= np.diff(segment_ids) == 0
    velocity[1:][valid] = np.diff(positions, axis=0)[valid] / dt[valid, None]
    velocity[~np.isfinite(velocity)] = 0.0
    return velocity


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


    timestamps = []
    positions = []
    velocities = []
    accelerations = []
    position_valid = []
    velocity_valid = []

    previous_position_reset = None
    previous_vertical_reset = None
    previous_invalid = False

    segment_ids = []
    segment = 0

    for record in records:

        timestamp = _finite(record.timestamp)

        if timestamp is None:
            continue

        if getattr(record, "coordinate_frame", "ENU") != "ENU":
            raise ValueError("Native trajectory adapters must supply ENU coordinates.")
        vertical_reset = record.vertical_reset_counter
        position_reset = record.position_reset_counter
        if previous_invalid or (
            previous_vertical_reset is not None and vertical_reset is not None
            and vertical_reset != previous_vertical_reset
        ) or (
            previous_position_reset is not None and position_reset is not None
            and position_reset != previous_position_reset
        ):
            segment += 1
        if vertical_reset is not None:
            previous_vertical_reset = vertical_reset
        if position_reset is not None:
            previous_position_reset = position_reset
        previous_invalid = not record.position_valid

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

        previous_invalid |= not all(value is not None for value in (x, y, z))
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
            segment_ids,
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

    records = _position_records_with_segments(evidence)

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

    segment_ids = np.asarray([item[4] for item in records], dtype=int)
    velocities = _derive_velocity(timestamps, positions, segment_ids)

    accelerations = np.zeros_like(
        positions,
        dtype=float,
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

    native_usable = any(
        record.position_valid and all(_finite(value) is not None for value in
                                      (record.timestamp, record.x_m, record.y_m, record.z_m))
        for record in native
    )
    if native_usable:
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

    features = trajectory_features(positions, velocities, position_valid)
    origin = {"kind": "source_estimator_local_origin"}
    if source == "derived":
        _, latitude, longitude, altitude = _extract_position_records(evidence)[0]
        origin = {"kind": "first_geodetic_observation", "latitude_deg": latitude,
                  "longitude_deg": longitude, "altitude_m": altitude}
    return TrajectoryDataset(
        timestamps=timestamps, positions=positions, velocities=velocities,
        features=features, feature_names=FEATURE_NAMES.copy(),
        segment_ids=segment_ids, accelerations=accelerations,
        trajectory_source=source,
        coordinate_origin=origin, source_platform=evidence.metadata.platform,
    )
