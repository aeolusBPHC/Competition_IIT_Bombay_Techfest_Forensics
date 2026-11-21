from dataclasses import asdict
from types import SimpleNamespace

import numpy as np
import pytest

from ml.synthetic_trajectory import SensorNoise, build_trajectory
from ml.synthetic_trajectory_dataset import load_synthetic_trajectory
from ml.trajectory_dataset import make_trajectory_windows, latest_history
from ml.trajectory_features import FEATURE_NAMES, TrajectoryDataset, build_trajectory_dataset, trajectory_features
from ml.trajectory_preprocessing import Standardizer, WindowTransform, rotate_xy
from platform_parsers.common.evidence_model import EvidenceMetadata, GPSRecord, NavigationRecord, NormalizedEvidence, TrajectoryRecord
from platform_parsers.px4.ulog_parser import PX4ULogParser


def linear_dataset(times=None):
    times = np.arange(0, 6.01, 0.1) if times is None else np.asarray(times)
    velocity = np.tile([2., 1., 0.5], (len(times), 1))
    positions = times[:, None] * velocity
    return TrajectoryDataset(times, positions, velocity, trajectory_features(positions, velocity),
                             FEATURE_NAMES.copy(), segment_ids=np.zeros(len(times), dtype=int))


def evidence(**kwargs):
    return NormalizedEvidence(EvidenceMetadata('test', 'PX4', 'ULog'), **kwargs)


def test_synthetic_v1_and_v2_window_contract(tmp_path):
    trajectory = build_trajectory(0, 'train', 'circle', 6., .1, 12, noisy=False)
    old = asdict(trajectory)
    for key in ('ground_truth_position', 'ground_truth_velocity', 'segment_ids', 'seed'):
        old.pop(key)
    path = tmp_path / 'legacy.npz'
    np.savez_compressed(path, **old)
    legacy = load_synthetic_trajectory(path)
    assert make_trajectory_windows(legacy, 20, 10).X.shape == (32, 20, 10)
    assert legacy.label_kind == 'noisy_observation'
    path = tmp_path / 'current.npz'
    np.savez_compressed(path, **asdict(trajectory), coordinate_frame='ENU')
    current = load_synthetic_trajectory(path)
    assert current.label_kind == 'simulation_ground_truth'
    current.ground_truth_positions += 100
    windows = make_trajectory_windows(current, 20, 10)
    np.testing.assert_allclose(windows.X[0], current.features[:20])
    np.testing.assert_allclose(windows.y[0], current.ground_truth_positions[20:30])
    np.testing.assert_allclose(current.subset(np.arange(5)).ground_truth_positions,
                               current.ground_truth_positions[:5])


def test_px4_converts_ned_to_enu_and_preserves_native_evidence():
    values = dict(timestamp=[1000000, 1100000], x=[10., 11.], y=[20., 22.], z=[-3., -3.5],
                  vx=[1., 1.], vy=[2., 2.], vz=[-.5, -.5], ax=[.1, .1], ay=[.2, .2], az=[-.3, -.3],
                  xy_valid=[True, True], z_valid=[True, True], v_xy_valid=[True, True], v_z_valid=[True, True])
    parser = object.__new__(PX4ULogParser)
    parser._dataset = lambda topic: SimpleNamespace(data=values)
    records = parser.extract_trajectory()
    assert (records[0].x_m, records[0].y_m, records[0].z_m) == (20., 10., 3.)
    assert (records[0].vx_m_s, records[0].vy_m_s, records[0].vz_m_s) == (2., 1., .5)
    assert (records[0].ax_m_s2, records[0].ay_m_s2, records[0].az_m_s2) == (.2, .1, .3)
    assert records[0].raw['x'] == 10. and records[0].raw['z'] == -3.
    dataset = build_trajectory_dataset(evidence(trajectory=records, gps=[GPSRecord(1., heading_deg=180.)]))
    # Course is velocity direction, not GPS antenna yaw.
    np.testing.assert_allclose(dataset.features[:, 7], 1 / np.sqrt(5))
    np.testing.assert_allclose(dataset.features[:, 8], 2 / np.sqrt(5))


def test_global_fallback_uses_same_axes_and_no_future_velocity():
    records = [NavigationRecord(0., 0., 0., 10.), NavigationRecord(.1, .000001, .000002, 11.)]
    dataset = build_trajectory_dataset(evidence(navigation=records))
    assert dataset.positions[1, 0] > dataset.positions[1, 1] > 0
    assert dataset.positions[1, 2] == 1
    np.testing.assert_array_equal(dataset.velocities[0], [0, 0, 0])
    assert dataset.coordinate_origin['latitude_deg'] == 0


def test_sparse_global_velocity_and_short_invalid_observation_boundary():
    records = [NavigationRecord(float(i), 0., i * .00001, 10.) for i in range(6)]
    dataset = build_trajectory_dataset(evidence(navigation=records))
    assert np.all(dataset.velocities[1:, 0] > 0)
    records[2].latitude_longitude_valid = False
    dataset = build_trajectory_dataset(evidence(navigation=records))
    assert dataset.segment_ids[1] != dataset.segment_ids[2]
    np.testing.assert_array_equal(dataset.velocities[2], [0., 0., 0.])


def test_missing_native_velocity_never_differentiates_across_invalidity_or_reset():
    records = [TrajectoryRecord(i * .1, x_m=float(i), y_m=0., z_m=0., position_valid=i != 2,
                                position_reset_counter=1 if i >= 4 else 0) for i in range(8)]
    records[3].x_m = 1000.
    records[4].x_m = 2000.
    dataset = build_trajectory_dataset(evidence(trajectory=records))
    np.testing.assert_array_equal(dataset.velocities[np.isclose(dataset.timestamps, .3)], [[0., 0., 0.]])
    np.testing.assert_array_equal(dataset.velocities[np.isclose(dataset.timestamps, .4)], [[0., 0., 0.]])
    assert len(set(dataset.segment_ids)) == 3


def test_inputs_never_interpolate_from_after_forecast_cutoff():
    dataset = linear_dataset([0., .14, .27, .4, .54, .67, .8, .94, 1.07, 1.2])
    first = make_trajectory_windows(dataset, 2, 1)
    np.testing.assert_array_equal(first.X[0, -1], dataset.features[0])  # cutoff 0.1
    dataset.features[1, :6] += 1000
    dataset.positions[1] += 1000
    second = make_trajectory_windows(dataset, 2, 1)
    np.testing.assert_array_equal(first.X[0], second.X[0])
    assert not np.allclose(first.y[0], second.y[0])


def test_invalid_observation_splits_even_a_short_gap():
    dataset = linear_dataset(np.arange(10) * .1)
    dataset.features[5, 9] = 0
    windows = make_trajectory_windows(dataset, 2, 2)
    assert len(windows.X) == 3
    assert not np.any((windows.input_timestamps < .5) & (windows.target_timestamps[:, -1] > .5))
    dataset.features[-1, 9] = 0
    with pytest.raises(ValueError, match='latest observation'):
        latest_history(dataset, 2, .1)


@pytest.mark.parametrize('mode', ['relative', 'residual_velocity', 'residual_acceleration'])
@pytest.mark.parametrize('frame', ['centered', 'heading'])
def test_transform_roundtrip_and_translation_invariance(mode, frame):
    windows = make_trajectory_windows(linear_dataset(), 20, 10)
    transform = WindowTransform(frame, mode)
    encoded = transform.targets(windows.y, windows.X)
    np.testing.assert_allclose(transform.absolute(encoded, windows.X), windows.y, atol=1e-12)
    shifted = windows.X.copy()
    shifted[..., :3] += [1000, -700, 400]
    np.testing.assert_allclose(transform.features(shifted), transform.features(windows.X), atol=1e-12)
    np.testing.assert_allclose(transform.targets(windows.y + [1000, -700, 400], shifted), encoded, atol=1e-12)
    if mode.startswith('residual'):
        np.testing.assert_allclose(encoded, 0, atol=1e-12)


def test_heading_transform_rotation_invariance():
    windows = make_trajectory_windows(linear_dataset(), 20, 10)
    angle = np.full(len(windows.X), 1.1)
    rotated = windows.X.copy()
    rotated[..., :3] = rotate_xy(rotated[..., :3], angle)
    rotated[..., 3:6] = rotate_xy(rotated[..., 3:6], angle)
    heading = np.arctan2(rotated[..., 7], rotated[..., 8]) + angle[:, None]
    rotated[..., 7], rotated[..., 8] = np.sin(heading), np.cos(heading)
    transform = WindowTransform('heading', 'relative')
    np.testing.assert_allclose(transform.features(rotated), transform.features(windows.X), atol=1e-12)


def test_scaler_roundtrip_and_absolute_target_guard():
    scaler = Standardizer()
    values = np.array([[[2., 3., 4.]], [[3., 5., 4.]]])
    scaler.fit(values)
    loaded = Standardizer.from_dict(scaler.to_dict())
    np.testing.assert_allclose(loaded.inverse_transform(loaded.transform(values)), values)
    with pytest.raises(ValueError, match='Absolute targets require'):
        WindowTransform('centered', 'absolute')


def test_sensor_noise_reproducible_and_ground_truth_is_separate():
    config = SensorNoise(dropout_probability=.1, outage_probability=1., reset_probability=1.)
    first = build_trajectory(1, 'test', 'circle', 10., .1, 99, noise=config)
    second = build_trajectory(1, 'test', 'circle', 10., .1, 99, noise=config)
    np.testing.assert_array_equal(first.position, second.position)
    assert np.any(first.position_valid == 0)
    assert len(set(first.segment_ids)) == 2
    assert not np.allclose(np.diff(first.timestamps), .1)
    assert np.all(np.isfinite(first.ground_truth_position))
    valid = first.position_valid.astype(bool)
    assert not np.allclose(first.position[valid], first.ground_truth_position[valid])
    assert not np.allclose(first.velocity[valid], first.ground_truth_velocity[valid])


def test_legacy_benchmark_helpers_preserve_reset_boundaries():
    from ml.trajectory_benchmark import generate_windows
    from ml.trajectory_quality import build_windows_for_range
    dataset = linear_dataset(np.arange(20) * .1)
    dataset.segment_ids[10:] = 1
    for helper in (generate_windows, build_windows_for_range):
        windows = helper(dataset, 0., 1.9, history_steps=5, prediction_steps=2, interval_s=.1)
        assert len(windows.X) == 8
        assert not np.any((windows.input_timestamps < 1.) & (windows.target_timestamps[:, -1] >= 1.))


def test_regular_grid_roundoff_does_not_add_sample_lag_after_reset():
    from ml.trajectory_baseline import constant_velocity_predict
    dataset = linear_dataset(np.arange(200) * .1)
    dataset.segment_ids[10:] = 1
    windows = make_trajectory_windows(dataset, 5, 2)
    np.testing.assert_allclose(constant_velocity_predict(windows.X, 2, .1), windows.y, atol=1e-12)
