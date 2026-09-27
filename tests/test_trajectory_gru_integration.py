import numpy as np

from ml.trajectory_features import TrajectoryDataset
from ml.trajectory_gru_train import (
    chronological_split,
    chronological_windows,
)


def make_trajectory(
    start=0.0,
    end=20.0,
    interval=0.1,
):
    timestamps = np.arange(
        start,
        end + interval / 2,
        interval,
    )

    positions = np.column_stack(
        (
            timestamps,
            2.0 * timestamps,
            -0.5 * timestamps,
        )
    )

    velocities = np.column_stack(
        (
            np.ones_like(timestamps),
            np.full_like(timestamps, 2.0),
            np.full_like(timestamps, -0.5),
        )
    )

    features = np.column_stack(
        (
            positions,
            velocities,
            np.linalg.norm(velocities, axis=1),
            np.zeros_like(timestamps),
            np.ones_like(timestamps),
            np.ones_like(timestamps),
        )
    )

    return TrajectoryDataset(
        timestamps=timestamps,
        positions=positions,
        velocities=velocities,
        features=features,
        feature_names=[
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
        ],
    )


def test_chronological_split_has_expected_order():
    trajectory = make_trajectory()

    split = chronological_split(trajectory)

    train_start, train_end = split["train"]
    val_start, val_end = split["validation"]
    test_start, test_end = split["test"]

    assert train_start < train_end
    assert train_end == val_start
    assert val_start < val_end
    assert val_end == test_start
    assert test_start < test_end


def test_gru_windows_do_not_cross_split_boundaries():
    trajectory = make_trajectory(
        start=0.0,
        end=100.0,
    )

    split = chronological_split(trajectory)

    windows = {}

    for name, (start, end) in split.items():
        windows[name] = chronological_windows(
            trajectory,
            start,
            end,
            history_steps=20,
            prediction_steps=10,
            interval_s=0.1,
        )

    train = windows["train"]
    validation = windows["validation"]
    test = windows["test"]

    # Every train target must remain inside train's interval.
    assert np.all(
        train.target_timestamps
        < split["train"][1] + 1e-9
    )

    # Every validation target must remain inside validation.
    assert np.all(
        validation.target_timestamps
        < split["validation"][1] + 1e-9
    )

    # Test is the final interval, so its endpoint may be included.
    assert np.all(
        test.target_timestamps
        <= split["test"][1] + 1e-9
    )

    # The first validation/test raw samples must not be reused
    # as the final train/validation samples.
    assert (
        np.max(train.input_timestamps)
        < np.min(validation.input_timestamps)
    )

    assert (
        np.max(validation.input_timestamps)
        < np.min(test.input_timestamps)
    )


def test_gru_windows_preserve_trajectory_metadata():
    trajectory = make_trajectory(
        start=0.0,
        end=100.0,
    )

    trajectory.segment_ids = np.zeros(
        len(trajectory.timestamps),
        dtype=int,
    )

    trajectory.accelerations = np.zeros_like(
        trajectory.positions
    )

    split = chronological_split(trajectory)

    windows = chronological_windows(
        trajectory,
        *split["train"],
        history_steps=20,
        prediction_steps=10,
        interval_s=0.1,
    )

    assert windows.X.shape[1:] == (20, 10)
    assert windows.y.shape[1:] == (10, 3)


def test_gru_split_windows_remain_platform_independent():
    trajectory = make_trajectory(
        start=0.0,
        end=100.0,
    )

    split = chronological_split(trajectory)

    for start, end in split.values():
        windows = chronological_windows(
            trajectory,
            start,
            end,
            history_steps=20,
            prediction_steps=10,
            interval_s=0.1,
        )

        assert windows.X.ndim == 3
        assert windows.y.ndim == 3
        assert windows.X.shape[-1] == 10
        assert windows.y.shape[-1] == 3
