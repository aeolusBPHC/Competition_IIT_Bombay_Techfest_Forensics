from __future__ import annotations

from pathlib import Path
import numpy as np

from ml.trajectory_features import (
    FEATURE_NAMES, TrajectoryDataset, trajectory_features,
)

# Kept as an alias for callers importing the old name.
SyntheticTrajectoryDataset = TrajectoryDataset


def load_synthetic_trajectory(path: str | Path) -> TrajectoryDataset:
    path = Path(path)
    with np.load(path, allow_pickle=False) as data:
        timestamps = np.asarray(data["timestamps"], dtype=float)
        positions = np.asarray(data["position"], dtype=float)
        velocities = np.asarray(data["velocity"], dtype=float)
        valid = np.asarray(data["position_valid"], dtype=bool)
        n = len(timestamps)
        if (timestamps.ndim != 1 or n < 2 or not np.all(np.isfinite(timestamps))
                or not np.all(np.diff(timestamps) > 0)):
            raise ValueError("At least two finite, strictly increasing timestamps are required.")
        if positions.shape != (n, 3) or velocities.shape != (n, 3) or valid.shape != (n,):
            raise ValueError("Trajectory position/velocity must be (N, 3), validity (N,).")
        frame = str(data["coordinate_frame"]) if "coordinate_frame" in data else "ENU"
        if frame != "ENU":
            raise ValueError("Synthetic trajectories must use ENU coordinates.")
        course = None
        if "heading_sin" in data and "heading_cos" in data:
            course = np.arctan2(data["heading_sin"], data["heading_cos"])
        features = trajectory_features(positions, velocities, valid, course)
        truth = (np.asarray(data["ground_truth_position"], dtype=float)
                 if "ground_truth_position" in data else None)
        if truth is not None and (truth.shape != (n, 3) or not np.all(np.isfinite(truth))):
            raise ValueError("Ground truth must be finite with shape (N, 3).")
        segments = (np.asarray(data["segment_ids"], dtype=int)
                    if "segment_ids" in data else np.zeros(n, dtype=int))
        if segments.shape != (n,):
            raise ValueError("segment_ids must have shape (N,).")
        return TrajectoryDataset(
            timestamps=timestamps, positions=positions, velocities=velocities,
            features=features, feature_names=FEATURE_NAMES.copy(),
            ground_truth_positions=truth, segment_ids=segments,
            trajectory_source="synthetic_measurement", coordinate_frame=frame,
            coordinate_origin={"kind": "simulation_world_origin"}, source_platform="synthetic",
            trajectory_id=str(data["trajectory_id"]), split=str(data["split"]),
            scenario=str(data["scenario"]),
            label_kind="simulation_ground_truth" if truth is not None else "noisy_observation",
        )


def load_synthetic_split(root: str | Path, split: str) -> list[TrajectoryDataset]:
    if split not in {"train", "validation", "test"}:
        raise ValueError("split must be train, validation, or test.")
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Synthetic dataset directory not found: {root}")
    datasets = []
    for path in sorted(root.glob("trajectory_*.npz")):
        dataset = load_synthetic_trajectory(path)
        if dataset.split == split:
            datasets.append(dataset)
    if not datasets:
        raise ValueError(f"No trajectories found for split '{split}'.")
    return datasets
