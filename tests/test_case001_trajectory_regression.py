from pathlib import Path

import numpy as np
import pytest

from platform_parsers.common.registry import ParserRegistry
from ml.trajectory_features import build_trajectory_dataset
from ml.trajectory_dataset import make_trajectory_windows


CASE001_PATH = Path(
    "repository/cases/CASE-001/"
    "EVD-20260919-175126/evidence/17_02_27.ulg"
)


@pytest.fixture(scope="module")
def case001_trajectory():
    assert CASE001_PATH.exists(), (
        f"CASE-001 evidence not found: {CASE001_PATH}"
    )

    registry = ParserRegistry()
    parser = registry.get_parser(CASE001_PATH)
    evidence = parser.parse()

    trajectory = build_trajectory_dataset(evidence)

    return evidence, trajectory


@pytest.fixture(scope="module")
def case001_windows(case001_trajectory):
    _, trajectory = case001_trajectory

    return make_trajectory_windows(
        trajectory,
        history_steps=20,
        prediction_steps=10,
        interval_s=0.1,
    )


def test_case001_uses_native_trajectory(case001_trajectory):
    evidence, trajectory = case001_trajectory

    # The PX4 parser must expose native trajectory records.
    assert len(evidence.trajectory) > 0

    # The ML dataset must consume the normalized/native trajectory path,
    # rather than falling back to GPS-derived trajectory data.
    assert trajectory.trajectory_source == "native_or_normalized"

    # Native trajectory data must contain 3D positions and velocities.
    assert trajectory.positions.shape[1] == 3
    assert trajectory.velocities.shape[1] == 3


def test_case001_velocity_has_no_extreme_artifact(case001_trajectory):
    _, trajectory = case001_trajectory

    speed = np.linalg.norm(
        trajectory.velocities,
        axis=1,
    )

    assert np.all(np.isfinite(speed))

    # CASE-001 previously produced a false ~233 m/s vertical-speed
    # artifact when velocity was derived from the global-position
    # altitude discontinuity. Native velocity must not contain it.
    assert np.max(speed) < 10.0

    # Stronger regression guard against the original artifact.
    assert not np.any(speed > 100.0)


def test_case001_windows_have_expected_temporal_structure(case001_windows):
    windows = case001_windows

    # 2 seconds history at 10 Hz.
    assert windows.X.shape[1:] == (20, 10)

    # 1 second prediction at 10 Hz, predicting x/y/z.
    assert windows.y.shape[1:] == (10, 3)

    # A substantial number of valid windows should remain after
    # continuity/reset handling.
    assert windows.X.shape[0] > 0

    # Each prediction sequence must advance at 0.1 s.
    target_dt = np.diff(
        windows.target_timestamps,
        axis=1,
    )

    assert np.allclose(
        target_dt,
        0.1,
        atol=1e-6,
    )

    # The first predicted point must occur exactly one interval
    # after the end of the observed history.
    assert np.isclose(
        windows.target_timestamps[0, 0]
        - windows.input_timestamps[0],
        0.1,
        atol=1e-6,
    )

    # The final prediction must also remain within the recorded
    # trajectory time range.
    assert (
        windows.target_timestamps[-1, -1]
        <= 2681.792 + 1e-6
    )
