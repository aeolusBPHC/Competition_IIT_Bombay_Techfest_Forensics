from pathlib import Path

import numpy as np
import pytest

from ml.trajectory_features import TrajectoryDataset
from ml.trajectory_dataset import make_trajectory_windows


def dataset_from_times(times, segment_ids=None):
    times = np.asarray(times, dtype=float)

    positions = np.column_stack(
        (
            times,
            times * 0.5,
            times * 0.1,
        )
    )

    velocities = np.zeros(
        (len(times), 3),
        dtype=float,
    )

    # 3 position + 3 velocity + 4 additional features = 10
    features = np.column_stack(
        (
            positions,
            velocities,
            np.ones((len(times), 4)),
        )
    )

    dataset = TrajectoryDataset(
        timestamps=times,
        positions=positions,
        velocities=velocities,
        features=features,
        feature_names=[
            f"f{i}"
            for i in range(features.shape[1])
        ],
    )

    if segment_ids is not None:
        dataset.segment_ids = np.asarray(
            segment_ids
        )

    return dataset


def test_windows_do_not_cross_segment_boundary():
    """
    Native reset/discontinuity segments must never be crossed
    by a supervised trajectory window.
    """

    times = np.arange(10, dtype=float) * 0.1

    dataset = dataset_from_times(
        times,
        [0] * 5 + [1] * 5,
    )

    windows = make_trajectory_windows(
        dataset,
        history_steps=3,
        prediction_steps=2,
        interval_s=0.1,
    )

    # Each 5-sample segment produces exactly one window:
    #
    # segment 0: 0.0 -> 0.4
    # segment 1: 0.5 -> 0.9
    assert len(windows.X) == 2

    assert np.allclose(
        windows.input_timestamps,
        [0.2, 0.7],
    )

    for target in windows.target_timestamps:
        assert not (
            target[0] < 0.5
            and target[-1] >= 0.5
        )


def test_windows_do_not_cross_large_timestamp_gap():
    """
    Missing-data gaps must not be bridged by interpolation.
    """

    times = np.concatenate(
        (
            np.arange(5, dtype=float) * 0.1,
            2.0 + np.arange(5, dtype=float) * 0.1,
        )
    )

    dataset = dataset_from_times(times)

    windows = make_trajectory_windows(
        dataset,
        history_steps=3,
        prediction_steps=2,
        interval_s=0.1,
    )

    # One window from each continuous chunk.
    assert len(windows.X) == 2

    for target in windows.target_timestamps:
        assert not (
            target[0] < 2.0
            and target[-1] >= 2.0
        )


def test_windows_do_not_cross_duplicate_or_reversed_timestamps():
    """
    Duplicate/reversed timestamps must create continuity boundaries
    rather than being interpolated through.
    """

    times = np.array(
        [
            0.0,
            0.1,
            0.2,
            0.2,  # duplicate
            0.1,  # reversed
            0.3,
            0.4,
            0.5,
            0.6,
        ]
    )

    dataset = dataset_from_times(times)

    windows = make_trajectory_windows(
        dataset,
        history_steps=2,
        prediction_steps=2,
        interval_s=0.1,
    )

    assert len(windows.X) > 0

    # Every individual target sequence must be strictly increasing.
    for target in windows.target_timestamps:
        assert np.all(
            np.diff(target) > 0
        )


def test_non_native_derived_trajectory_without_segment_ids_still_works():
    """
    Non-native/derived trajectory sources do not need native reset
    metadata. Timestamp continuity alone must be sufficient.
    """

    times = np.arange(12, dtype=float) * 0.1

    dataset = dataset_from_times(times)

    windows = make_trajectory_windows(
        dataset,
        history_steps=3,
        prediction_steps=2,
        interval_s=0.1,
    )

    assert windows.X.shape == (
        8,
        3,
        10,
    )

    assert windows.y.shape == (
        8,
        2,
        3,
    )

    assert windows.target_mode == "absolute"


def test_case001_windows_do_not_cross_known_gap_or_reset():
    """
    Regression test against the actual CASE-001 PX4 evidence.

    Known discontinuities:

    - horizontal position validity gap:
        934.300 -> 943.716 s

    - native reset boundary:
        approximately 1193.448 -> 1193.456 s
    """

    path = Path(
        "repository/cases/CASE-001/"
        "EVD-20260919-175126/"
        "evidence/17_02_27.ulg"
    )

    if not path.exists():
        pytest.skip(
            "CASE-001 evidence is not available"
        )

    from platform_parsers.common.registry import (
        ParserRegistry,
    )

    from ml.trajectory_features import (
        build_trajectory_dataset,
    )

    evidence = (
        ParserRegistry()
        .get_parser(path)
        .parse()
    )

    trajectory = build_trajectory_dataset(
        evidence
    )

    windows = make_trajectory_windows(
        trajectory,
        history_steps=20,
        prediction_steps=10,
        interval_s=0.1,
    )

    # No target may cross the known invalid-data gap.
    for target in windows.target_timestamps:
        assert not (
            target[0] < 943.716
            and target[-1] >= 943.716
        )

    # No target may cross the native reset boundary.
    for target in windows.target_timestamps:
        assert not (
            target[0] < 1193.456
            and target[-1] >= 1193.456
        )
