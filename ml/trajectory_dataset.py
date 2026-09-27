from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ml.trajectory_features import TrajectoryDataset


@dataclass
class TrajectoryWindows:
    """Supervised sequence dataset for trajectory prediction."""

    X: np.ndarray
    y: np.ndarray

    input_timestamps: np.ndarray
    target_timestamps: np.ndarray

    target_mode: str = "absolute"


def _regular_time_grid(
    timestamps: np.ndarray,
    interval_s: float,
) -> np.ndarray:
    """Create a regular time grid spanning continuous observations."""

    if interval_s <= 0:
        raise ValueError("interval_s must be positive.")

    if len(timestamps) < 2:
        raise ValueError(
            "At least two timestamps are required."
        )

    start = float(timestamps[0])
    end = float(timestamps[-1])

    if end <= start:
        raise ValueError(
            "Trajectory timestamps must increase."
        )

    # Use a small numerical tolerance before flooring. Without
    # this, values such as 0.4 / 0.1 can become 3.999999999...
    # and incorrectly produce one fewer grid point.
    span = end - start
    count = int(
        np.floor(
            span / interval_s
            + 1e-9
        )
    ) + 1

    return start + np.arange(count) * interval_s


def _resample_features(
    dataset: TrajectoryDataset,
    interval_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Interpolate trajectory features onto a regular time grid.

    This function is intended for a single continuous trajectory
    chunk. Large temporal gaps must be removed before reaching here.
    """

    grid = _regular_time_grid(
        dataset.timestamps,
        interval_s,
    )

    features = np.empty(
        (len(grid), dataset.features.shape[1]),
        dtype=float,
    )

    for column in range(dataset.features.shape[1]):
        features[:, column] = np.interp(
            grid,
            dataset.timestamps,
            dataset.features[:, column],
        )

    return grid, features


def _continuous_chunks(
    dataset: TrajectoryDataset,
    interval_s: float,
    max_gap_s: float | None = None,
) -> list[np.ndarray]:
    """
    Split a trajectory into temporally continuous chunks.

    A new chunk starts when:

    1. segment_ids changes;
    2. timestamps are non-increasing;
    3. the timestamp gap exceeds max_gap_s.

    segment_ids are optional. This keeps the function platform
    independent: native platforms may provide reset-aware segments,
    while derived/non-native trajectories can rely on timestamps.
    """

    timestamps = np.asarray(
        dataset.timestamps,
        dtype=float,
    )

    if len(timestamps) == 0:
        return []

    if max_gap_s is None:
        # At the normal 0.1 s training interval this gives a
        # 0.25 s maximum interpolation gap. This is deliberately
        # much smaller than the ~9 s invalid-data gap observed in
        # CASE-001.
        max_gap_s = max(
            2.5 * interval_s,
            0.25,
        )

    if max_gap_s <= 0:
        raise ValueError(
            "max_gap_s must be positive."
        )

    segment_ids = getattr(
        dataset,
        "segment_ids",
        None,
    )

    if segment_ids is not None:
        segment_ids = np.asarray(segment_ids)

        if len(segment_ids) != len(timestamps):
            segment_ids = None

    boundaries = []

    if len(timestamps) > 1:
        dt = np.diff(timestamps)

        for index, delta in enumerate(dt, start=1):
            split = False

            # Never interpolate across duplicate or reversed time.
            if not np.isfinite(delta) or delta <= 0:
                split = True

            # Never interpolate across a large missing-data gap.
            elif delta > max_gap_s:
                split = True

            # Native reset / discontinuity boundary.
            if (
                segment_ids is not None
                and segment_ids[index] != segment_ids[index - 1]
            ):
                split = True

            if split:
                boundaries.append(index)

    starts = [0] + boundaries
    ends = boundaries + [len(timestamps)]

    chunks = []

    for start, end in zip(starts, ends):
        if end - start >= 2:
            chunks.append(
                np.arange(start, end)
            )

    return chunks


def _make_windows_for_chunk(
    dataset: TrajectoryDataset,
    history_steps: int,
    prediction_steps: int,
    interval_s: float,
    target_mode: str,
) -> TrajectoryWindows:
    """
    Build windows from one continuous trajectory chunk.

    No reset or temporal-gap checking is required here because the
    caller has already established continuity.
    """

    timestamps, features = _resample_features(
        dataset,
        interval_s,
    )

    positions = features[:, :3]

    required = (
        history_steps
        + prediction_steps
    )

    if len(features) < required:
        return TrajectoryWindows(
            X=np.empty(
                (0, history_steps, features.shape[1]),
                dtype=float,
            ),
            y=np.empty(
                (0, prediction_steps, 3),
                dtype=float,
            ),
            input_timestamps=np.empty(
                (0,),
                dtype=float,
            ),
            target_timestamps=np.empty(
                (0, prediction_steps),
                dtype=float,
            ),
            target_mode=target_mode,
        )

    X = []
    y = []
    input_times = []
    target_times = []

    max_start = (
        len(features)
        - history_steps
        - prediction_steps
        + 1
    )

    for start in range(max_start):
        input_end = (
            start + history_steps
        )

        target_end = (
            input_end + prediction_steps
        )

        history = features[
            start:input_end
        ]

        future_positions = positions[
            input_end:target_end
        ]

        if target_mode == "absolute":
            target = future_positions

        else:
            last_observed_position = positions[
                input_end - 1
            ]

            target = (
                future_positions
                - last_observed_position
            )

        X.append(history)
        y.append(target)

        input_times.append(
            timestamps[input_end - 1]
        )

        target_times.append(
            timestamps[
                input_end:target_end
            ]
        )

    return TrajectoryWindows(
        X=np.asarray(X, dtype=float),
        y=np.asarray(y, dtype=float),
        input_timestamps=np.asarray(
            input_times,
            dtype=float,
        ),
        target_timestamps=np.asarray(
            target_times,
            dtype=float,
        ),
        target_mode=target_mode,
    )


def make_trajectory_windows(
    dataset: TrajectoryDataset,
    history_steps: int,
    prediction_steps: int,
    interval_s: float = 0.1,
    target_mode: str = "absolute",
    max_gap_s: float | None = None,
) -> TrajectoryWindows:
    """
    Build fixed-length supervised trajectory sequences.

    The trajectory is first divided into continuous chunks.

    Windows are never allowed to:

    - cross a native reset/discontinuity segment;
    - cross a large timestamp gap;
    - cross duplicate/reversed timestamps.

    This is platform independent. Native trajectory sources can
    provide ``segment_ids``; derived/non-native sources do not need
    them and are protected by temporal continuity checks.

    X shape:
        (samples, history_steps, features)

    y shape:
        (samples, prediction_steps, 3)

    target_mode="absolute":
        y contains future x/y/z positions.

    target_mode="relative":
        y contains future displacement relative to the final
        observed history position.
    """

    if history_steps <= 0:
        raise ValueError(
            "history_steps must be positive."
        )

    if prediction_steps <= 0:
        raise ValueError(
            "prediction_steps must be positive."
        )

    if target_mode not in {
        "absolute",
        "relative",
    }:
        raise ValueError(
            "target_mode must be 'absolute' or 'relative'."
        )

    chunks = _continuous_chunks(
        dataset,
        interval_s=interval_s,
        max_gap_s=max_gap_s,
    )

    if not chunks:
        raise ValueError(
            "No continuous trajectory chunks contain "
            "at least two samples."
        )

    all_X = []
    all_y = []
    all_input_times = []
    all_target_times = []

    for indices in chunks:
        chunk = type(dataset)(
            timestamps=dataset.timestamps[indices],
            positions=dataset.positions[indices],
            velocities=dataset.velocities[indices],
            features=dataset.features[indices],
            feature_names=dataset.feature_names,
        )

        # Preserve optional platform-independent trajectory metadata.
        for name in (
            "segment_ids",
            "accelerations",
        ):
            values = getattr(
                dataset,
                name,
                None,
            )

            if values is not None:
                setattr(
                    chunk,
                    name,
                    np.asarray(values)[indices],
                )

        windows = _make_windows_for_chunk(
            chunk,
            history_steps=history_steps,
            prediction_steps=prediction_steps,
            interval_s=interval_s,
            target_mode=target_mode,
        )

        if len(windows.X) == 0:
            continue

        all_X.append(windows.X)
        all_y.append(windows.y)
        all_input_times.append(
            windows.input_timestamps
        )
        all_target_times.append(
            windows.target_timestamps
        )

    if not all_X:
        raise ValueError(
            "No valid trajectory windows could be constructed. "
            "The trajectory may be too short after continuity filtering."
        )

    return TrajectoryWindows(
        X=np.concatenate(
            all_X,
            axis=0,
        ),
        y=np.concatenate(
            all_y,
            axis=0,
        ),
        input_timestamps=np.concatenate(
            all_input_times,
            axis=0,
        ),
        target_timestamps=np.concatenate(
            all_target_times,
            axis=0,
        ),
        target_mode=target_mode,
    )
