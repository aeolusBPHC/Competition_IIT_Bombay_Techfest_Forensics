from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class SyntheticTrajectoryDataset:
    """TrajectoryDataset-compatible representation of one synthetic trajectory."""

    timestamps: np.ndarray
    features: np.ndarray
    trajectory_id: str
    split: str
    scenario: str


def load_synthetic_trajectory(
    path: str | Path,
) -> SyntheticTrajectoryDataset:
    """
    Load one synthetic trajectory and convert it into the
    same feature representation used by the platform-independent
    trajectory prediction pipeline.

    Features:

        0  x_m
        1  y_m
        2  z_m
        3  vx_m_s
        4  vy_m_s
        5  vz_m_s
        6  speed_m_s
        7  heading_sin
        8  heading_cos
        9  position_valid
    """

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Synthetic trajectory not found: {path}"
        )

    data = np.load(path)

    timestamps = np.asarray(
        data["timestamps"],
        dtype=float,
    )

    position = np.asarray(
        data["position"],
        dtype=float,
    )

    velocity = np.asarray(
        data["velocity"],
        dtype=float,
    )

    speed = np.asarray(
        data["speed"],
        dtype=float,
    )

    heading_sin = np.asarray(
        data["heading_sin"],
        dtype=float,
    )

    heading_cos = np.asarray(
        data["heading_cos"],
        dtype=float,
    )

    position_valid = np.asarray(
        data["position_valid"],
        dtype=float,
    )

    if position.ndim != 2 or position.shape[1] != 3:
        raise ValueError(
            "position must have shape (N, 3)."
        )

    if velocity.ndim != 2 or velocity.shape[1] != 3:
        raise ValueError(
            "velocity must have shape (N, 3)."
        )

    n = len(timestamps)

    arrays = [
        position,
        velocity,
        speed,
        heading_sin,
        heading_cos,
        position_valid,
    ]

    if any(len(array) != n for array in arrays):
        raise ValueError(
            "All trajectory arrays must have the same length."
        )

    if n < 2:
        raise ValueError(
            "A trajectory must contain at least two samples."
        )

    if not np.all(np.diff(timestamps) > 0):
        raise ValueError(
            "Trajectory timestamps must be strictly increasing."
        )

    features = np.column_stack(
        [
            position[:, 0],
            position[:, 1],
            position[:, 2],
            velocity[:, 0],
            velocity[:, 1],
            velocity[:, 2],
            speed,
            heading_sin,
            heading_cos,
            position_valid,
        ]
    )

    trajectory_id = str(
        data["trajectory_id"]
    )

    split = str(
        data["split"]
    )

    scenario = str(
        data["scenario"]
    )

    return SyntheticTrajectoryDataset(
        timestamps=timestamps,
        features=features,
        trajectory_id=trajectory_id,
        split=split,
        scenario=scenario,
    )


def load_synthetic_split(
    root: str | Path,
    split: str,
) -> list[SyntheticTrajectoryDataset]:
    """
    Load all synthetic trajectories belonging to a split.

    Valid splits:

        train
        validation
        test
    """

    if split not in {
        "train",
        "validation",
        "test",
    }:
        raise ValueError(
            "split must be 'train', 'validation', or 'test'."
        )

    root = Path(root)

    if not root.exists():
        raise FileNotFoundError(
            f"Synthetic dataset directory not found: {root}"
        )

    datasets = []

    for path in sorted(
        root.glob("trajectory_*.npz")
    ):
        dataset = load_synthetic_trajectory(path)

        if dataset.split == split:
            datasets.append(dataset)

    if not datasets:
        raise ValueError(
            f"No trajectories found for split '{split}'."
        )

    return datasets
