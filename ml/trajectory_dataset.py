from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from ml.trajectory_features import TrajectoryDataset


@dataclass
class TrajectoryWindows:
    """Raw observed histories and absolute or relative future target positions."""

    X: np.ndarray
    y: np.ndarray
    input_timestamps: np.ndarray
    target_timestamps: np.ndarray
    target_mode: str = "absolute"


def _regular_time_grid(timestamps, interval_s):
    if not np.isfinite(interval_s) or interval_s <= 0:
        raise ValueError("interval_s must be positive and finite.")
    if len(timestamps) < 2 or not np.all(np.isfinite(timestamps)):
        raise ValueError("At least two finite timestamps are required.")
    if not np.all(np.diff(timestamps) > 0):
        raise ValueError("Trajectory timestamps must increase.")
    count = int(np.floor((timestamps[-1] - timestamps[0]) / interval_s + 1e-9)) + 1
    return timestamps[0] + np.arange(count) * interval_s


def _features_at(dataset, grid):
    # Hold the last available observation. Linear interpolation would use
    # samples after a forecast cutoff when the source clock is irregular.
    # Equivalent decimal timestamps can differ by a few floating-point ULPs
    # after a segment's grid is rebuilt. Do not add a whole sample of lag.
    tolerance = 4 * np.finfo(float).eps * np.maximum(1.0, np.abs(grid))
    indices = np.searchsorted(dataset.timestamps, grid + tolerance, side="right") - 1
    return dataset.features[np.clip(indices, 0, len(dataset.timestamps) - 1)].copy()


def _resample_features(dataset, interval_s):
    grid = _regular_time_grid(dataset.timestamps, interval_s)
    return grid, _features_at(dataset, grid)


def _continuous_chunks(dataset, interval_s, max_gap_s=None):
    if not np.isfinite(interval_s) or interval_s <= 0:
        raise ValueError("interval_s must be positive and finite.")
    if max_gap_s is None:
        max_gap_s = max(2.5 * interval_s, 0.25)
    if not np.isfinite(max_gap_s) or max_gap_s <= 0:
        raise ValueError("max_gap_s must be positive and finite.")
    times = np.asarray(dataset.timestamps)
    n = len(times)
    if dataset.coordinate_frame != "ENU":
        raise ValueError("Trajectory datasets must use ENU coordinates.")
    if dataset.features.ndim != 2 or len(dataset.features) != n:
        raise ValueError("Features must have shape (N, feature_count).")
    if len(dataset.feature_names) != dataset.features.shape[1]:
        raise ValueError("Feature names do not match the feature matrix.")
    if dataset.positions.shape != (n, 3) or dataset.velocities.shape != (n, 3):
        raise ValueError("Positions and velocities must have shape (N, 3).")
    if dataset.ground_truth_positions is not None and (
        dataset.ground_truth_positions.shape != (n, 3)
        or not np.all(np.isfinite(dataset.ground_truth_positions))
    ):
        raise ValueError("Ground truth must be finite with shape (N, 3).")
    valid = np.isfinite(times) & np.all(np.isfinite(dataset.features), axis=1)
    if "position_valid" in dataset.feature_names:
        valid &= dataset.features[:, dataset.feature_names.index("position_valid")] >= 1.0
    segments = dataset.segment_ids
    if segments is not None and np.asarray(segments).shape != (n,):
        raise ValueError("segment_ids must have shape (N,).")
    chunks = []
    start = None
    for i in range(n):
        continuous = (
            i > 0 and valid[i - 1] and valid[i]
            and 0 < times[i] - times[i - 1] <= max_gap_s
            and (segments is None or segments[i] == segments[i - 1])
        )
        if not continuous and start is not None:
            if i - start >= 2:
                chunks.append(np.arange(start, i))
            start = None
        if valid[i] and start is None:
            start = i
    if start is not None and n - start >= 2:
        chunks.append(np.arange(start, n))
    return chunks


def _make_windows_for_chunk(dataset, history_steps, prediction_steps, interval_s, target_mode):
    times, features = _resample_features(dataset, interval_s)
    labels = dataset.ground_truth_positions
    if labels is None:
        labels = dataset.positions
    # Targets may be interpolated from future records. They are kept
    # separate from the causal observation features above.
    labels = np.column_stack([
        np.interp(times, dataset.timestamps, labels[:, axis]) for axis in range(3)
    ])
    count = max(0, len(times) - history_steps - prediction_steps + 1)
    X = np.empty((count, history_steps, features.shape[1]))
    y = np.empty((count, prediction_steps, 3))
    input_times = np.empty(count)
    target_times = np.empty((count, prediction_steps))
    for start in range(count):
        end = start + history_steps
        X[start] = features[start:end]
        y[start] = labels[end:end + prediction_steps]
        if target_mode == "relative":
            y[start] -= X[start, -1, :3]
        input_times[start] = times[end - 1]
        target_times[start] = times[end:end + prediction_steps]
    return TrajectoryWindows(X, y, input_times, target_times, target_mode)


def make_trajectory_windows(dataset, history_steps, prediction_steps, interval_s=0.1,
                            target_mode="absolute", max_gap_s=None):
    """Build windows within valid continuous segments; never bridge a reset,
    invalid observation, reversed timestamp, duplicate timestamp or large gap.
    Clean labels, if supplied, never enter X.
    """
    if history_steps <= 0 or prediction_steps <= 0:
        raise ValueError("history_steps and prediction_steps must be positive.")
    if target_mode not in {"absolute", "relative"}:
        raise ValueError("target_mode must be 'absolute' or 'relative'.")
    windows = []
    for indices in _continuous_chunks(dataset, interval_s, max_gap_s):
        window = _make_windows_for_chunk(
            dataset.subset(indices), history_steps, prediction_steps, interval_s, target_mode,
        )
        if len(window.X):
            windows.append(window)
    if not windows:
        raise ValueError("No valid trajectory windows after continuity filtering; trajectory may be too short.")
    return TrajectoryWindows(
        **{name: np.concatenate([getattr(w, name) for w in windows])
           for name in ("X", "y", "input_timestamps", "target_timestamps")},
        target_mode=target_mode,
    )


def chronological_split(trajectory, train_ratio=0.70, validation_ratio=0.15):
    if not (0 < train_ratio < 1 and 0 < validation_ratio < 1 - train_ratio):
        raise ValueError("Split ratios must be positive and leave a nonempty test fraction.")
    start, end = float(trajectory.timestamps[0]), float(trajectory.timestamps[-1])
    duration = end - start
    return {
        "train": (start, start + duration * train_ratio),
        "validation": (start + duration * train_ratio,
                       start + duration * (train_ratio + validation_ratio)),
        "test": (start + duration * (train_ratio + validation_ratio), end),
    }


def slice_time_range(dataset, start_time, end_time):
    """Half-open splits, except that the final recorded endpoint is retained."""
    right = (dataset.timestamps <= end_time + 1e-9 if end_time >= dataset.timestamps[-1] - 1e-9
             else dataset.timestamps < end_time)
    indices = np.flatnonzero((dataset.timestamps >= start_time) & right)
    if not len(indices):
        raise ValueError(f"No trajectory samples in [{start_time}, {end_time}].")
    return dataset.subset(indices)


def chronological_windows(trajectory, start_time, end_time, history_steps,
                          prediction_steps, interval_s, target_mode="absolute"):
    return make_trajectory_windows(
        slice_time_range(trajectory, start_time, end_time), history_steps,
        prediction_steps, interval_s, target_mode,
    )


def latest_history(dataset, history_steps, interval_s):
    """Inference needs only observations, including the final source sample."""
    chunks = _continuous_chunks(dataset, interval_s)
    if (not chunks or chunks[-1][-1] != len(dataset.timestamps) - 1
            or history_steps < 2):
        raise ValueError("The latest observation must belong to a valid continuous history.")
    chunk = dataset.subset(chunks[-1])
    grid = chunk.timestamps[-1] - np.arange(history_steps - 1, -1, -1) * interval_s
    if grid[0] < chunk.timestamps[0] - 1e-9:
        raise ValueError("Insufficient recent continuous history for this checkpoint.")
    return _features_at(chunk, grid)[None, ...], grid
