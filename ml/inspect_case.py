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


def main():
    print("=" * 70)
    print("CASE-003 TRAJECTORY ML INSPECTION")
    print("=" * 70)
    print()

    print(f"Input: {INPUT}")
    print(f"Exists: {INPUT.exists()}")
    print()

    parser = PX4ULogParser(INPUT)
    evidence = parser.parse()

    print("NORMALIZED EVIDENCE")
    print("-" * 70)
    print(f"GPS records:        {len(evidence.gps)}")
    print(f"Navigation records: {len(evidence.navigation)}")
    print()

    dataset = build_trajectory_dataset(evidence)

    print("TRAJECTORY DATASET")
    print("-" * 70)
    print(f"Trajectory points: {len(dataset.timestamps)}")
    print(f"Feature shape:     {dataset.features.shape}")
    print(f"Feature names:")
    for i, name in enumerate(dataset.feature_names):
        print(f"  {i}: {name}")
    print()

    if len(dataset.timestamps) == 0:
        print("ERROR: No valid trajectory points were extracted.")
        return

    timestamps = dataset.timestamps
    positions = dataset.positions
    velocities = dataset.velocities

    print("TIME")
    print("-" * 70)
    print(f"Start:              {timestamps[0]:.3f} s")
    print(f"End:                {timestamps[-1]:.3f} s")
    print(f"Duration:            {timestamps[-1] - timestamps[0]:.3f} s")
    print()

    if len(timestamps) > 1:
        dt = np.diff(timestamps)

        print("SAMPLING")
        print("-" * 70)
        print(f"Mean dt:             {np.mean(dt):.6f} s")
        print(f"Median dt:           {np.median(dt):.6f} s")
        print(f"Min dt:              {np.min(dt):.6f} s")
        print(f"Max dt:              {np.max(dt):.6f} s")
        print()

    print("POSITION")
    print("-" * 70)
    print(
        f"X range:             "
        f"{np.min(positions[:, 0]):.3f} to "
        f"{np.max(positions[:, 0]):.3f} m"
    )
    print(
        f"Y range:             "
        f"{np.min(positions[:, 1]):.3f} to "
        f"{np.max(positions[:, 1]):.3f} m"
    )
    print(
        f"Z range:             "
        f"{np.min(positions[:, 2]):.3f} to "
        f"{np.max(positions[:, 2]):.3f} m"
    )
    print()

    speed = np.linalg.norm(velocities, axis=1)

    print("VELOCITY")
    print("-" * 70)
    print(f"Mean speed:          {np.mean(speed):.3f} m/s")
    print(f"Median speed:        {np.median(speed):.3f} m/s")
    print(f"Maximum speed:       {np.max(speed):.3f} m/s")
    print()

    print("WINDOW GENERATION")
    print("-" * 70)

    interval = 0.1
    history_steps = 20
    prediction_steps = 10

    windows = make_trajectory_windows(
        dataset,
        interval_s=interval,
        history_steps=history_steps,
        prediction_steps=prediction_steps,
    )

    print(f"Interval:            {interval} s")
    print(f"History:             {history_steps} steps")
    print(f"History duration:    {history_steps * interval:.1f} s")
    print(f"Prediction:          {prediction_steps} steps")
    print(f"Prediction horizon:  {prediction_steps * interval:.1f} s")
    print(f"X shape:             {windows.X.shape}")
    print(f"y shape:             {windows.y.shape}")
    print()

    if len(windows.X) == 0:
        print("ERROR: No trajectory windows were generated.")
        return

    print("CONSTANT-VELOCITY BASELINE")
    print("-" * 70)

    predictions = constant_velocity_predict(
        windows.X,
        prediction_steps=prediction_steps,
        interval_s=interval,
    )

    ade = average_displacement_error(
        predictions,
        windows.y,
    )

    fde = final_displacement_error(
        predictions,
        windows.y,
    )

    print(f"ADE:                 {ade:.4f} m")
    print(f"FDE:                 {fde:.4f} m")
    print()

    print("=" * 70)
    print("INSPECTION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
