from __future__ import annotations

import numpy as np


def _validate_trajectory_input(
    X: np.ndarray,
    prediction_steps: int,
    interval_s: float,
) -> None:
    if X.ndim != 3:
        raise ValueError(
            "X must have shape "
            "(samples, history_steps, features)."
        )

    if X.shape[2] < 6:
        raise ValueError(
            "X must contain position and velocity features."
        )

    if X.shape[1] < 2:
        raise ValueError(
            "X must contain at least two history steps."
        )

    if prediction_steps <= 0:
        raise ValueError(
            "prediction_steps must be positive."
        )

    if interval_s <= 0:
        raise ValueError(
            "interval_s must be positive."
        )


def constant_velocity_predict(
    X: np.ndarray,
    prediction_steps: int,
    interval_s: float,
) -> np.ndarray:
    """
    Predict future x/y/z using the latest observed velocity.

    X shape:
        (samples, history_steps, features)

    Required feature order:
        x_m, y_m, z_m, vx_m_s, vy_m_s, vz_m_s, ...
    """

    _validate_trajectory_input(
        X,
        prediction_steps,
        interval_s,
    )

    position = X[:, -1, :3]
    velocity = X[:, -1, 3:6]

    predictions = []

    for step in range(1, prediction_steps + 1):
        predictions.append(
            position
            + velocity * (step * interval_s)
        )

    return np.stack(
        predictions,
        axis=1,
    )


def constant_acceleration_predict(
    X: np.ndarray,
    prediction_steps: int,
    interval_s: float,
) -> np.ndarray:
    """
    Predict future x/y/z using the latest observed velocity
    and a constant-acceleration estimate.

    Acceleration is estimated from the final two observed
    velocity samples:

        a = (v_t - v_(t-dt)) / dt

    Future position is predicted using:

        p(tau) = p_0 + v_0 * tau + 0.5 * a * tau^2

    X shape:
        (samples, history_steps, features)

    Required feature order:
        x_m, y_m, z_m, vx_m_s, vy_m_s, vz_m_s, ...
    """

    _validate_trajectory_input(
        X,
        prediction_steps,
        interval_s,
    )

    position = X[:, -1, :3]
    velocity_now = X[:, -1, 3:6]
    velocity_previous = X[:, -2, 3:6]

    acceleration = (
        velocity_now - velocity_previous
    ) / interval_s

    predictions = []

    for step in range(1, prediction_steps + 1):
        tau = step * interval_s

        predictions.append(
            position
            + velocity_now * tau
            + 0.5 * acceleration * tau * tau
        )

    return np.stack(
        predictions,
        axis=1,
    )


def average_displacement_error(
    predicted: np.ndarray,
    actual: np.ndarray,
) -> float:
    """Calculate Average Displacement Error (ADE) in metres."""

    predicted = np.asarray(predicted, dtype=float)
    actual = np.asarray(actual, dtype=float)

    if predicted.shape != actual.shape:
        raise ValueError(
            "Predicted and actual arrays must have "
            "the same shape."
        )

    distances = np.linalg.norm(
        predicted - actual,
        axis=-1,
    )

    return float(np.mean(distances))


def final_displacement_error(
    predicted: np.ndarray,
    actual: np.ndarray,
) -> float:
    """Calculate Final Displacement Error (FDE) in metres."""

    predicted = np.asarray(predicted, dtype=float)
    actual = np.asarray(actual, dtype=float)

    if predicted.shape != actual.shape:
        raise ValueError(
            "Predicted and actual arrays must have "
            "the same shape."
        )

    distances = np.linalg.norm(
        predicted[:, -1] - actual[:, -1],
        axis=-1,
    )

    return float(np.mean(distances))
