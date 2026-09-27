import numpy as np

from ml.trajectory_baseline import (
    average_displacement_error,
    constant_velocity_predict,
    final_displacement_error,
)
from ml.trajectory_dataset import (
    make_trajectory_windows,
)
from ml.trajectory_features import (
    TrajectoryDataset,
)


def make_linear_dataset():
    timestamps = np.arange(
        0.0,
        10.1,
        0.1,
    )

    positions = np.column_stack(
        (
            timestamps * 2.0,
            timestamps * 3.0,
            timestamps * 0.5,
        )
    )

    velocities = np.tile(
        np.array([2.0, 3.0, 0.5]),
        (len(timestamps), 1),
    )

    features = np.column_stack(
        (
            positions,
            velocities,
            np.linalg.norm(
                velocities,
                axis=1,
            ),
            np.zeros(len(timestamps)),
            np.ones(len(timestamps)),
            np.ones(len(timestamps)),
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


def test_window_shapes():
    dataset = make_linear_dataset()

    windows = make_trajectory_windows(
        dataset,
        history_steps=10,
        prediction_steps=5,
        interval_s=0.1,
    )

    assert windows.X.ndim == 3
    assert windows.y.ndim == 3

    assert windows.X.shape[1] == 10
    assert windows.X.shape[2] == 10

    assert windows.y.shape[1] == 5
    assert windows.y.shape[2] == 3


def test_constant_velocity_predicts_linear_motion():
    dataset = make_linear_dataset()

    windows = make_trajectory_windows(
        dataset,
        history_steps=10,
        prediction_steps=5,
        interval_s=0.1,
    )

    predicted = constant_velocity_predict(
        windows.X,
        prediction_steps=5,
        interval_s=0.1,
    )

    assert predicted.shape == windows.y.shape

    assert np.allclose(
        predicted,
        windows.y,
        atol=1e-8,
    )


def test_perfect_prediction_has_zero_error():
    dataset = make_linear_dataset()

    windows = make_trajectory_windows(
        dataset,
        history_steps=10,
        prediction_steps=5,
        interval_s=0.1,
    )

    assert (
        average_displacement_error(
            windows.y,
            windows.y,
        )
        == 0.0
    )

    assert (
        final_displacement_error(
            windows.y,
            windows.y,
        )
        == 0.0
    )
