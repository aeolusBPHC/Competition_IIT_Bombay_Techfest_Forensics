"""Serializable, observation-only transforms shared by training and inference."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import numpy as np

from ml.trajectory_baseline import constant_acceleration_predict, constant_velocity_predict


class Standardizer:
    def __init__(self):
        self.mean_ = None
        self.std_ = None

    def fit(self, values):
        flat = np.asarray(values).reshape(-1, values.shape[-1])
        if not len(flat) or not np.all(np.isfinite(flat)):
            raise ValueError("Scaler training values must be nonempty and finite.")
        self.mean_ = flat.mean(axis=0)
        self.std_ = flat.std(axis=0)
        self.std_[self.std_ < 1e-8] = 1.0

    def transform(self, values):
        if self.mean_ is None:
            raise RuntimeError("Standardizer has not been fitted.")
        return (values - self.mean_) / self.std_

    def inverse_transform(self, values):
        if self.mean_ is None:
            raise RuntimeError("Standardizer has not been fitted.")
        return values * self.std_ + self.mean_

    def to_dict(self):
        return {"mean": self.mean_.tolist(), "std": self.std_.tolist()}

    @classmethod
    def from_dict(cls, data):
        result = cls()
        result.mean_ = np.asarray(data["mean"], dtype=float)
        result.std_ = np.asarray(data["std"], dtype=float)
        if (result.mean_.ndim != 1 or result.mean_.shape != result.std_.shape
                or not np.all(np.isfinite(result.mean_))
                or not np.all(np.isfinite(result.std_)) or np.any(result.std_ <= 0)):
            raise ValueError("Invalid checkpoint standardization statistics.")
        return result


def rotate_xy(values, angles):
    result = np.array(values, dtype=float, copy=True)
    cos, sin = np.cos(angles)[:, None], np.sin(angles)[:, None]
    result[..., 0] = cos * values[..., 0] - sin * values[..., 1]
    result[..., 1] = sin * values[..., 0] + cos * values[..., 1]
    return result


@dataclass(frozen=True)
class WindowTransform:
    input_frame: str = "centered"
    target_mode: str = "residual_velocity"
    interval_s: float = 0.1

    def __post_init__(self):
        if self.input_frame not in {"global", "centered", "heading"}:
            raise ValueError("input_frame must be global, centered, or heading.")
        if self.target_mode not in {"absolute", "relative", "residual_velocity", "residual_acceleration"}:
            raise ValueError("Unknown target mode.")
        if self.target_mode == "absolute" and self.input_frame != "global":
            raise ValueError("Absolute targets require --input-frame global; use relative or residual targets with centered inputs.")
        if not np.isfinite(self.interval_s) or self.interval_s <= 0:
            raise ValueError("interval_s must be positive and finite.")

    def angles(self, X):
        if self.input_frame != "heading":
            return np.zeros(len(X))
        # Choose the most recent reliable velocity using observed history only.
        horizontal = X[..., 3:5]
        reliable = np.linalg.norm(horizontal, axis=-1) >= 0.1
        indices = np.max(np.where(reliable, np.arange(X.shape[1]), -1), axis=1)
        velocity = horizontal[np.arange(len(X)), np.maximum(indices, 0)]
        return np.where(indices >= 0, np.arctan2(velocity[:, 1], velocity[:, 0]), 0.0)

    def features(self, X):
        result = np.array(X, dtype=float, copy=True)
        if self.input_frame != "global":
            result[..., :3] -= X[:, -1:, :3]
        angles = -self.angles(X)
        result[..., :3] = rotate_xy(result[..., :3], angles)
        result[..., 3:6] = rotate_xy(result[..., 3:6], angles)
        course = np.arctan2(X[..., 7], X[..., 8]) + angles[:, None]
        result[..., 7], result[..., 8] = np.sin(course), np.cos(course)
        return result

    def reference(self, X, prediction_steps):
        if self.target_mode == "residual_velocity":
            return constant_velocity_predict(X, prediction_steps, self.interval_s)
        if self.target_mode == "residual_acceleration":
            return constant_acceleration_predict(X, prediction_steps, self.interval_s)
        if self.target_mode == "relative":
            return X[:, -1:, :3]
        return np.zeros((len(X), 1, 3))

    def targets(self, absolute_positions, X):
        residual = absolute_positions - self.reference(X, absolute_positions.shape[1])
        return rotate_xy(residual, -self.angles(X))

    def absolute(self, transformed_positions, X):
        return (rotate_xy(transformed_positions, self.angles(X))
                + self.reference(X, transformed_positions.shape[1]))

    def to_dict(self):
        return asdict(self)
