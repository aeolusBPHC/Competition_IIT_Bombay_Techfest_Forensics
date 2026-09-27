from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from platform_parsers.px4.ulog_parser import PX4ULogParser
from ml.trajectory_features import build_trajectory_dataset
from ml.trajectory_dataset import make_trajectory_windows
from ml.trajectory_baseline import (
    constant_velocity_predict,
    average_displacement_error,
    final_displacement_error,
)


INPUT = Path(
    "repository/cases/CASE-003/raw/px4_sitl_qgc_mission.ulg"
)

OUTPUT = Path(
    "repository/cases/CASE-003/reports/"
    "CASE-003_trajectory_benchmark.json"
)


def make_subdataset(dataset, start_time, end_time):
    mask = (
        (dataset.timestamps >= start_time)
        & (dataset.timestamps <= end_time)
    )

    indices = np.flatnonzero(mask)

    if len(indices) == 0:
        return None

    return type(dataset)(
        timestamps=dataset.timestamps[indices],
        positions=dataset.positions[indices],
        velocities=dataset.velocities[indices],
        features=dataset.features[indices],
        feature_names=dataset.feature_names,
    )


def generate_windows(
    dataset,
    start_time,
    end_time,
    history_steps,
    prediction_steps,
    interval_s,
):
    subdataset = make_subdataset(
        dataset,
        start_time,
        end_time,
    )

    if subdataset is None:
        return None

    return make_trajectory_windows(
        subdataset,
        history_steps=history_steps,
        prediction_steps=prediction_steps,
        interval_s=interval_s,
    )


def calculate_metrics(predictions, actual):
    errors = np.linalg.norm(
        predictions - actual,
        axis=2,
    )

    return {
        "ADE_m": float(np.mean(errors)),
        "FDE_m": float(np.mean(errors[:, -1])),
        "horizon_error_m": [
            float(value)
            for value in np.mean(errors, axis=0)
        ],
    }


def classify_windows(
    windows,
    stationary_threshold=0.10,
    moving_threshold=0.50,
):
    """
    Classify a prediction window according to the mean speed
    during its history portion.

    This deliberately uses only the observed history and does not
    inspect the future target trajectory.
    """

    speed = np.linalg.norm(
        windows.X[:, :, 3:6],
        axis=2,
    )

    mean_history_speed = np.mean(speed, axis=1)

    stationary = (
        mean_history_speed < stationary_threshold
    )

    moving = (
        mean_history_speed >= moving_threshold
    )

    intermediate = ~(stationary | moving)

    return {
        "stationary": stationary,
        "moving": moving,
        "intermediate": intermediate,
        "mean_history_speed": mean_history_speed,
    }


def evaluate_subset(predictions, actual, mask):
    count = int(np.sum(mask))

    if count == 0:
        return {
            "window_count": 0,
            "ADE_m": None,
            "FDE_m": None,
            "horizon_error_m": [],
        }

    return {
        "window_count": count,
        **calculate_metrics(
            predictions[mask],
            actual[mask],
        ),
    }


def main():
    print("=" * 72)
    print("CASE-003 TRAJECTORY BENCHMARK")
    print("=" * 72)
    print()

    print(f"Input:  {INPUT}")
    print(f"Output: {OUTPUT}")
    print()

    parser = PX4ULogParser(INPUT)
    evidence = parser.parse()
    dataset = build_trajectory_dataset(evidence)

    timestamps = np.asarray(
        dataset.timestamps,
        dtype=float,
    )

    positions = np.asarray(
        dataset.positions,
        dtype=float,
    )

    velocities = np.asarray(
        dataset.velocities,
        dtype=float,
    )

    duration = timestamps[-1] - timestamps[0]

    # ---------------------------------------------------------------
    # Chronological split
    # ---------------------------------------------------------------

    train_end = timestamps[0] + 0.70 * duration
    validation_end = timestamps[0] + 0.85 * duration

    test_start = validation_end
    test_end = timestamps[-1]

    # ---------------------------------------------------------------
    # Window configuration
    # ---------------------------------------------------------------

    interval_s = 0.1
    history_steps = 20
    prediction_steps = 10

    history_duration_s = (
        history_steps * interval_s
    )

    prediction_horizon_s = (
        prediction_steps * interval_s
    )

    print("DATA")
    print("-" * 72)
    print(f"Trajectory points:      {len(timestamps):,}")
    print(f"Start:                  {timestamps[0]:.3f} s")
    print(f"End:                    {timestamps[-1]:.3f} s")
    print(f"Duration:               {duration:.3f} s")
    print()

    # ---------------------------------------------------------------
    # Timestamp quality
    # ---------------------------------------------------------------

    dt = np.diff(timestamps)

    timestamp_quality = {
        "duplicate_timestamps": int(np.sum(dt == 0)),
        "backward_timestamps": int(np.sum(dt < 0)),
        "min_dt_s": float(np.min(dt)),
        "max_dt_s": float(np.max(dt)),
        "mean_dt_s": float(np.mean(dt)),
        "median_dt_s": float(np.median(dt)),
    }

    # ---------------------------------------------------------------
    # Position quality
    # ---------------------------------------------------------------

    displacement = np.linalg.norm(
        np.diff(positions, axis=0),
        axis=1,
    )

    position_quality = {
        "mean_step_displacement_m": float(
            np.mean(displacement)
        ),
        "median_step_displacement_m": float(
            np.median(displacement)
        ),
        "p95_step_displacement_m": float(
            np.percentile(displacement, 95)
        ),
        "maximum_step_displacement_m": float(
            np.max(displacement)
        ),
        "jumps_over_1m": int(
            np.sum(displacement > 1.0)
        ),
    }

    # ---------------------------------------------------------------
    # Acceleration
    # ---------------------------------------------------------------

    acceleration = np.zeros_like(velocities)

    dv = np.diff(velocities, axis=0)
    valid_dt = dt > 0

    acceleration[1:][valid_dt] = (
        dv[valid_dt]
        / dt[valid_dt, None]
    )

    acceleration_magnitude = np.linalg.norm(
        acceleration,
        axis=1,
    )

    max_acceleration_index = int(
        np.argmax(acceleration_magnitude)
    )

    acceleration_quality = {
        "mean_m_s2": float(
            np.mean(acceleration_magnitude)
        ),
        "median_m_s2": float(
            np.median(acceleration_magnitude)
        ),
        "p95_m_s2": float(
            np.percentile(
                acceleration_magnitude,
                95,
            )
        ),
        "p99_m_s2": float(
            np.percentile(
                acceleration_magnitude,
                99,
            )
        ),
        "maximum_m_s2": float(
            acceleration_magnitude[
                max_acceleration_index
            ]
        ),
        "maximum_timestamp_s": float(
            timestamps[max_acceleration_index]
        ),
    }

    # ---------------------------------------------------------------
    # Motion distribution
    # ---------------------------------------------------------------

    speed = np.linalg.norm(
        velocities,
        axis=1,
    )

    stationary_threshold = 0.10
    moving_threshold = 0.50

    stationary_points = speed < stationary_threshold
    moving_points = speed >= moving_threshold
    intermediate_points = ~(
        stationary_points
        | moving_points
    )

    motion_quality = {
        "stationary_threshold_m_s":
            stationary_threshold,
        "moving_threshold_m_s":
            moving_threshold,
        "stationary_percentage":
            float(100.0 * np.mean(stationary_points)),
        "moving_percentage":
            float(100.0 * np.mean(moving_points)),
        "intermediate_percentage":
            float(100.0 * np.mean(intermediate_points)),
        "mean_speed_m_s":
            float(np.mean(speed)),
        "median_speed_m_s":
            float(np.median(speed)),
        "p95_speed_m_s":
            float(np.percentile(speed, 95)),
        "maximum_speed_m_s":
            float(np.max(speed)),
    }

    # ---------------------------------------------------------------
    # Generate windows
    # ---------------------------------------------------------------

    train_windows = generate_windows(
        dataset,
        timestamps[0],
        train_end,
        history_steps,
        prediction_steps,
        interval_s,
    )

    validation_windows = generate_windows(
        dataset,
        train_end,
        validation_end,
        history_steps,
        prediction_steps,
        interval_s,
    )

    test_windows = generate_windows(
        dataset,
        test_start,
        test_end,
        history_steps,
        prediction_steps,
        interval_s,
    )

    if test_windows is None:
        raise RuntimeError(
            "No test windows were generated."
        )

    # ---------------------------------------------------------------
    # Constant velocity test prediction
    # ---------------------------------------------------------------

    predictions = constant_velocity_predict(
        test_windows.X,
        prediction_steps=prediction_steps,
        interval_s=interval_s,
    )

    actual = test_windows.y

    overall = calculate_metrics(
        predictions,
        actual,
    )

    # ---------------------------------------------------------------
    # Motion classification
    # ---------------------------------------------------------------

    motion = classify_windows(
        test_windows,
        stationary_threshold,
        moving_threshold,
    )

    stationary_results = evaluate_subset(
        predictions,
        actual,
        motion["stationary"],
    )

    moving_results = evaluate_subset(
        predictions,
        actual,
        motion["moving"],
    )

    intermediate_results = evaluate_subset(
        predictions,
        actual,
        motion["intermediate"],
    )

    # ---------------------------------------------------------------
    # Benchmark artifact
    # ---------------------------------------------------------------

    result = {
        "schema_version": "1.0",
        "case_id": "CASE-003",
        "evidence": str(INPUT),
        "model": {
            "name": "constant_velocity",
            "type": "kinematic_baseline",
        },
        "trajectory": {
            "points": int(len(timestamps)),
            "start_time_s": float(timestamps[0]),
            "end_time_s": float(timestamps[-1]),
            "duration_s": float(duration),
        },
        "sampling": {
            "source_dt_s": float(np.median(dt)),
            "source_rate_hz": float(
                1.0 / np.median(dt)
            ),
            "resampled_interval_s": interval_s,
        },
        "window_configuration": {
            "history_steps": history_steps,
            "history_duration_s": history_duration_s,
            "prediction_steps": prediction_steps,
            "prediction_horizon_s": prediction_horizon_s,
            "feature_count": int(
                test_windows.X.shape[2]
            ),
        },
        "chronological_split": {
            "train": {
                "start_s": float(timestamps[0]),
                "end_s": float(train_end),
                "window_count": int(
                    len(train_windows.X)
                ) if train_windows is not None else 0,
            },
            "validation": {
                "start_s": float(train_end),
                "end_s": float(validation_end),
                "window_count": int(
                    len(validation_windows.X)
                )
                if validation_windows is not None
                else 0,
            },
            "test": {
                "start_s": float(test_start),
                "end_s": float(test_end),
                "window_count": int(
                    len(test_windows.X)
                ),
            },
        },
        "quality": {
            "timestamps": timestamp_quality,
            "positions": position_quality,
            "acceleration": acceleration_quality,
            "motion": motion_quality,
        },
        "test_results": {
            "overall": overall,
            "stationary": stationary_results,
            "moving": moving_results,
            "intermediate": intermediate_results,
        },
    }

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            result,
            handle,
            indent=2,
        )

    # ---------------------------------------------------------------
    # Terminal summary
    # ---------------------------------------------------------------

    print("QUALITY")
    print("-" * 72)

    print(
        "Duplicate timestamps:   "
        f"{timestamp_quality['duplicate_timestamps']}"
    )

    print(
        "Backward timestamps:    "
        f"{timestamp_quality['backward_timestamps']}"
    )

    print(
        "Position jumps > 1 m:   "
        f"{position_quality['jumps_over_1m']}"
    )

    print(
        "Acceleration median:    "
        f"{acceleration_quality['median_m_s2']:.4f} m/s²"
    )

    print(
        "Acceleration p95:       "
        f"{acceleration_quality['p95_m_s2']:.4f} m/s²"
    )

    print(
        "Acceleration p99:       "
        f"{acceleration_quality['p99_m_s2']:.4f} m/s²"
    )

    print(
        "Maximum acceleration:   "
        f"{acceleration_quality['maximum_m_s2']:.4f} m/s²"
    )

    print(
        "Maximum acceleration at:"
        f" {acceleration_quality['maximum_timestamp_s']:.3f} s"
    )

    print()

    print("TEST BASELINE")
    print("-" * 72)

    print(
        f"Overall windows:        "
        f"{overall['ADE_m']:.6f} m ADE | "
        f"{overall['FDE_m']:.6f} m FDE"
    )

    print(
        f"Stationary windows:     "
        f"{stationary_results['window_count']:,} | "
        f"{stationary_results['ADE_m']:.6f} m ADE | "
        f"{stationary_results['FDE_m']:.6f} m FDE"
    )

    print(
        f"Moving windows:         "
        f"{moving_results['window_count']:,} | "
        f"{moving_results['ADE_m']:.6f} m ADE | "
        f"{moving_results['FDE_m']:.6f} m FDE"
    )

    print(
        f"Intermediate windows:   "
        f"{intermediate_results['window_count']:,} | "
        f"{intermediate_results['ADE_m']:.6f} m ADE | "
        f"{intermediate_results['FDE_m']:.6f} m FDE"
    )

    print()

    print("ERROR BY HORIZON")
    print("-" * 72)

    for index, error in enumerate(
        overall["horizon_error_m"],
        start=1,
    ):
        print(
            f"t + {index * interval_s:.1f} s: "
            f"{error:.6f} m"
        )

    print()

    print(f"Saved benchmark: {OUTPUT}")

    print()
    print("=" * 72)
    print("BENCHMARK COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
