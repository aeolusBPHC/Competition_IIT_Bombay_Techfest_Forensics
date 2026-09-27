from __future__ import annotations

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


def percentile(values, q):
    if len(values) == 0:
        return float("nan")
    return float(np.percentile(values, q))


def describe(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]

    if len(values) == 0:
        return {
            "count": 0,
            "mean": float("nan"),
            "median": float("nan"),
            "p95": float("nan"),
            "max": float("nan"),
        }

    return {
        "count": len(values),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "p95": percentile(values, 95),
        "max": float(np.max(values)),
    }


def build_windows_for_range(
    dataset,
    start_time,
    end_time,
    history_steps=20,
    prediction_steps=10,
    interval_s=0.1,
):
    """
    Create windows only if the complete history + prediction interval
    lies inside the requested chronological range.
    """

    timestamps = dataset.timestamps

    mask = (
        (timestamps >= start_time)
        & (timestamps <= end_time)
    )

    indices = np.flatnonzero(mask)

    if len(indices) == 0:
        return None

    sub_dataset = type(dataset)(
        timestamps=timestamps[indices],
        positions=dataset.positions[indices],
        velocities=dataset.velocities[indices],
        features=dataset.features[indices],
        feature_names=dataset.feature_names,
    )

    return make_trajectory_windows(
        sub_dataset,
        history_steps=history_steps,
        prediction_steps=prediction_steps,
        interval_s=interval_s,
    )


def main():
    print("=" * 72)
    print("CASE-003 TRAJECTORY QUALITY + CHRONOLOGICAL BENCHMARK")
    print("=" * 72)
    print()

    print(f"Input: {INPUT}")
    print(f"Exists: {INPUT.exists()}")
    print()

    # ---------------------------------------------------------------
    # Parse
    # ---------------------------------------------------------------

    parser = PX4ULogParser(INPUT)
    evidence = parser.parse()
    dataset = build_trajectory_dataset(evidence)

    timestamps = np.asarray(dataset.timestamps, dtype=float)
    positions = np.asarray(dataset.positions, dtype=float)
    velocities = np.asarray(dataset.velocities, dtype=float)

    if len(timestamps) == 0:
        raise RuntimeError("No trajectory points were extracted.")

    # ---------------------------------------------------------------
    # Basic trajectory information
    # ---------------------------------------------------------------

    print("1. BASIC TRAJECTORY")
    print("-" * 72)

    duration = timestamps[-1] - timestamps[0]

    print(f"Points:              {len(timestamps):,}")
    print(f"Start time:          {timestamps[0]:.3f} s")
    print(f"End time:            {timestamps[-1]:.3f} s")
    print(f"Duration:            {duration:.3f} s")
    print()

    # ---------------------------------------------------------------
    # Timestamp quality
    # ---------------------------------------------------------------

    dt = np.diff(timestamps)

    duplicate_count = int(np.sum(dt == 0))
    negative_count = int(np.sum(dt < 0))
    positive_dt = dt[dt > 0]

    print("2. TIMESTAMP QUALITY")
    print("-" * 72)

    print(f"Duplicate timestamps:     {duplicate_count:,}")
    print(f"Backward timestamps:      {negative_count:,}")

    if len(positive_dt):
        print(f"Minimum positive dt:      {np.min(positive_dt):.9f} s")
        print(f"Maximum dt:               {np.max(positive_dt):.9f} s")
        print(f"Mean dt:                  {np.mean(positive_dt):.9f} s")
        print(f"Median dt:                {np.median(positive_dt):.9f} s")

    print()

    # ---------------------------------------------------------------
    # Position quality
    # ---------------------------------------------------------------

    position_delta = np.diff(positions, axis=0)
    displacement = np.linalg.norm(position_delta, axis=1)

    print("3. POSITION QUALITY")
    print("-" * 72)

    pos_stats = describe(displacement)

    print(
        f"Step displacement mean:  "
        f"{pos_stats['mean']:.6f} m"
    )
    print(
        f"Step displacement median: "
        f"{pos_stats['median']:.6f} m"
    )
    print(
        f"Step displacement p95:    "
        f"{pos_stats['p95']:.6f} m"
    )
    print(
        f"Maximum step displacement: "
        f"{pos_stats['max']:.6f} m"
    )

    large_jump_threshold = 1.0
    large_jumps = displacement > large_jump_threshold

    print(
        f"Jumps > {large_jump_threshold:.1f} m:        "
        f"{np.sum(large_jumps):,}"
    )
    print()

    # ---------------------------------------------------------------
    # Velocity / acceleration
    # ---------------------------------------------------------------

    speed = np.linalg.norm(velocities, axis=1)

    acceleration = np.zeros_like(velocities)

    if len(timestamps) > 1:
        dv = np.diff(velocities, axis=0)
        dtime = np.diff(timestamps)

        valid = dtime > 0

        acceleration[1:][valid] = (
            dv[valid] / dtime[valid, None]
        )

    acceleration_magnitude = np.linalg.norm(
        acceleration,
        axis=1,
    )

    print("4. VELOCITY / ACCELERATION")
    print("-" * 72)

    speed_stats = describe(speed)
    accel_stats = describe(acceleration_magnitude)

    print(
        f"Speed mean:             "
        f"{speed_stats['mean']:.4f} m/s"
    )
    print(
        f"Speed median:           "
        f"{speed_stats['median']:.4f} m/s"
    )
    print(
        f"Speed p95:              "
        f"{speed_stats['p95']:.4f} m/s"
    )
    print(
        f"Maximum speed:          "
        f"{speed_stats['max']:.4f} m/s"
    )
    print()

    print(
        f"Acceleration mean:      "
        f"{accel_stats['mean']:.4f} m/s²"
    )
    print(
        f"Acceleration median:    "
        f"{accel_stats['median']:.4f} m/s²"
    )
    print(
        f"Acceleration p95:       "
        f"{accel_stats['p95']:.4f} m/s²"
    )
    print(
        f"Maximum acceleration:   "
        f"{accel_stats['max']:.4f} m/s²"
    )
    print()

    # ---------------------------------------------------------------
    # Stationary / moving analysis
    # ---------------------------------------------------------------

    stationary_threshold = 0.10
    moving_threshold = 0.50

    stationary = speed < stationary_threshold
    moving = speed >= moving_threshold

    stationary_percentage = (
        100.0 * np.mean(stationary)
    )

    moving_percentage = (
        100.0 * np.mean(moving)
    )

    print("5. MOTION REGIMES")
    print("-" * 72)

    print(
        f"Stationary (< {stationary_threshold:.2f} m/s): "
        f"{stationary_percentage:.2f}%"
    )
    print(
        f"Moving (>= {moving_threshold:.2f} m/s):       "
        f"{moving_percentage:.2f}%"
    )
    print(
        f"Intermediate:                              "
        f"{100.0 - stationary_percentage - moving_percentage:.2f}%"
    )
    print()

    # ---------------------------------------------------------------
    # Altitude / takeoff / landing approximation
    # ---------------------------------------------------------------

    altitude = positions[:, 2]

    altitude_rate = np.zeros_like(altitude)

    if len(timestamps) > 1:
        dz = np.diff(altitude)
        dtime = np.diff(timestamps)

        valid = dtime > 0
        altitude_rate[1:][valid] = (
            dz[valid] / dtime[valid]
        )

    print("6. ALTITUDE")
    print("-" * 72)

    print(f"Minimum altitude:       {np.min(altitude):.3f} m")
    print(f"Maximum altitude:       {np.max(altitude):.3f} m")
    print(f"Final altitude:         {altitude[-1]:.3f} m")
    print(
        f"Maximum climb rate:     "
        f"{np.max(altitude_rate):.3f} m/s"
    )
    print(
        f"Maximum descent rate:   "
        f"{np.min(altitude_rate):.3f} m/s"
    )
    print()

    # ---------------------------------------------------------------
    # Chronological split
    # ---------------------------------------------------------------

    train_end = timestamps[0] + 0.70 * duration
    validation_end = timestamps[0] + 0.85 * duration
    test_end = timestamps[-1]

    print("7. CHRONOLOGICAL SPLIT")
    print("-" * 72)

    print(
        f"TRAIN:       "
        f"{timestamps[0]:.3f} -> {train_end:.3f} s"
    )
    print(
        f"VALIDATION:  "
        f"{train_end:.3f} -> {validation_end:.3f} s"
    )
    print(
        f"TEST:        "
        f"{validation_end:.3f} -> {test_end:.3f} s"
    )
    print()

    # ---------------------------------------------------------------
    # Window generation
    # ---------------------------------------------------------------

    interval_s = 0.1
    history_steps = 20
    prediction_steps = 10

    print("8. CHRONOLOGICAL WINDOWS")
    print("-" * 72)

    train_windows = build_windows_for_range(
        dataset,
        timestamps[0],
        train_end,
        history_steps,
        prediction_steps,
        interval_s,
    )

    validation_windows = build_windows_for_range(
        dataset,
        train_end,
        validation_end,
        history_steps,
        prediction_steps,
        interval_s,
    )

    test_windows = build_windows_for_range(
        dataset,
        validation_end,
        test_end,
        history_steps,
        prediction_steps,
        interval_s,
    )

    for name, windows in (
        ("TRAIN", train_windows),
        ("VALIDATION", validation_windows),
        ("TEST", test_windows),
    ):
        if windows is None:
            print(f"{name}: no windows")
        else:
            print(
                f"{name}: {len(windows.X):,} windows | "
                f"X={windows.X.shape} | "
                f"y={windows.y.shape}"
            )

    print()

    # ---------------------------------------------------------------
    # Test baseline
    # ---------------------------------------------------------------

    print("9. CONSTANT-VELOCITY TEST BENCHMARK")
    print("-" * 72)

    if test_windows is None or len(test_windows.X) == 0:
        raise RuntimeError(
            "No test windows were generated."
        )

    predictions = constant_velocity_predict(
        test_windows.X,
        prediction_steps=prediction_steps,
        interval_s=interval_s,
    )

    ade = average_displacement_error(
        predictions,
        test_windows.y,
    )

    fde = final_displacement_error(
        predictions,
        test_windows.y,
    )

    print(f"Test ADE:              {ade:.6f} m")
    print(f"Test FDE:              {fde:.6f} m")
    print()

    # ---------------------------------------------------------------
    # Test by prediction horizon
    # ---------------------------------------------------------------

    horizon_errors = np.linalg.norm(
        predictions - test_windows.y,
        axis=2,
    )

    print("10. ERROR BY PREDICTION HORIZON")
    print("-" * 72)

    for i, error in enumerate(
        np.mean(horizon_errors, axis=0),
        start=1,
    ):
        print(
            f"t + {i * interval_s:.1f} s: "
            f"{error:.6f} m"
        )

    print()

    print("=" * 72)
    print("QUALITY ANALYSIS + BENCHMARK COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
