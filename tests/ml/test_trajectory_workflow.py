import json
from pathlib import Path

import numpy as np
import pytest
import torch

from ml.synthetic_trajectory import SensorNoise, generate_dataset
from ml.trajectory_data import read_manifest, load_training_data
from ml.trajectory_evaluation import bootstrap_mean_ci, grouped_metrics
from ml.trajectory_gru_train import main as train
from ml.trajectory_inference import TrajectoryPredictor, main as infer
from ml.trajectory_provenance import ensure_distinct_outputs


def clean_noise():
    return SensorNoise(**{key: 0. for key in SensorNoise.__dataclass_fields__})


@pytest.fixture
def dataset(tmp_path):
    root = tmp_path / 'data'
    generate_dataset(root, train_count=2, validation_count=2, test_count=2,
                     duration_s=8., seed=100, noise=clean_noise())
    return root


def test_manifest_rejects_flight_content_and_mission_leakage(dataset):
    path = dataset / 'manifest.json'
    data = json.loads(path.read_text())
    data['test'][0]['flight_id'] = data['train'][0]['flight_id']
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Duplicate flight_id'):
        read_manifest(path)
    data['test'][0]['flight_id'] = 'different-name'
    data['test'][0]['path'] = data['train'][0]['path']
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Duplicate path'):
        read_manifest(path)
    copied = dataset / 'renamed.npz'
    copied.write_bytes((dataset / data['train'][0]['path']).read_bytes())
    data['test'][0]['path'] = copied.name
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Duplicate sha256'):
        read_manifest(path)
    data['test'][0]['path'] = 'trajectory_004.npz'
    data['test'][0]['mission'] = data['train'][0]['mission']
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='crosses'):
        read_manifest(path, holdout_group='mission')


def test_bootstrap_uses_flights_not_overlapping_windows():
    assert bootstrap_mean_ci([1.]) is None
    predicted = np.zeros((101, 2, 3))
    actual = np.zeros_like(predicted)
    actual[:100, :, 0], actual[100, :, 0] = 1., 9.
    grouped = grouped_metrics(predicted, actual, np.asarray(['a'] * 100 + ['b']))
    assert np.mean([value['ade_m'] for value in grouped.values()]) == 5.
    interval = bootstrap_mean_ci([1., 9.])
    assert interval['lower'] <= 5 <= interval['upper']


def test_train_repeated_seeds_reload_and_cli_forecast(dataset, tmp_path):
    checkpoint, output = tmp_path / 'model.pt', tmp_path / 'benchmark.json'
    result = train([
        '--manifest', str(dataset / 'manifest.json'), '--holdout-group', 'mission',
        '--case-id', 'TEST', '--output', str(output), '--model-output', str(checkpoint),
        '--epochs', '2', '--hidden-size', '8', '--layers', '1', '--seeds', '7', '8',
        '--input-frame', 'heading', '--threads', '1',
    ])
    assert len(result['runs']) == 2
    assert (tmp_path / 'model.seed-8.pt').is_file()
    assert result['aggregate']['models']['gru']['flight_count'] == 2
    assert result['aggregate']['models']['gru']['flight_bootstrap_95_ci']['ade_m'] is not None
    assert result['provenance']['dependencies']['torch']
    assert result['provenance']['source_sha256']['ml/trajectory_dataset.py']
    assert all(entry['sha256'] for entry in result['provenance']['data']['sources'])
    predictor = TrajectoryPredictor(checkpoint)
    chosen = min(result['runs'][0]['validation'], key=lambda key:
                 result['runs'][0]['validation'][key]['flight_macro']['ade_m'])
    assert predictor.checkpoint['recommended_predictor'] == chosen
    blocks, _ = load_training_data(manifest=dataset / 'manifest.json')
    np.testing.assert_allclose(predictor.feature_scaler.mean_,
                               predictor.transform.features(blocks['train']['X']).reshape(-1, 10).mean(axis=0))
    np.testing.assert_allclose(predictor.target_scaler.mean_,
                               predictor.transform.targets(blocks['train']['y'], blocks['train']['X']).reshape(-1, 3).mean(axis=0))
    X = blocks['test']['X'][:4]
    before = predictor.predict(X, 'gru')
    np.testing.assert_allclose(TrajectoryPredictor(checkpoint).predict(X, 'gru'), before, atol=1e-8)
    shifted = X.copy()
    shifted[..., :3] += [100, 20, -10]
    np.testing.assert_allclose(predictor.predict(shifted, 'gru'), before + [100, 20, -10], atol=1e-5)
    # Saved test errors must match inference using the saved preprocessing.
    all_predictions = predictor.predict(blocks['test']['X'], 'gru')
    ade = np.linalg.norm(all_predictions - blocks['test']['y'], axis=-1).mean()
    assert ade == pytest.approx(result['test']['gru']['overall']['ade_m'], abs=1e-6)
    forecast, report = tmp_path / 'forecast.json', tmp_path / 'forecast.html'
    prediction = infer(['--input', str(dataset / 'trajectory_004.npz'), '--checkpoint', str(checkpoint),
                        '--output', str(forecast), '--report', str(report), '--case-id', '<case>', '--at-time', '5'])
    assert prediction['forecast']['kind'] == 'model_estimates'
    assert prediction['forecast']['recorded_evidence'] is False
    assert prediction['forecast']['cutoff_timestamp_s'] <= 5
    assert prediction['forecast']['timestamps_s'][0] > 5
    assert prediction['source']['sha256']
    with np.load(dataset / 'trajectory_004.npz', allow_pickle=False) as source:
        changed = dict(source)
    changed['position'][changed['timestamps'] > 5] += 10000
    changed['velocity'][changed['timestamps'] > 5] += 10000
    changed_path = tmp_path / 'future_changed.npz'
    np.savez_compressed(changed_path, **changed)
    changed_forecast = infer(['--input', str(changed_path), '--checkpoint', str(checkpoint),
                             '--output', str(tmp_path / 'changed_forecast.json'), '--at-time', '5'])
    assert changed_forecast['forecast']['positions_m'] == prediction['forecast']['positions_m']
    html = report.read_text()
    assert 'not recorded evidence' in html
    assert '&lt;case&gt;' in html and '<case>' not in html
    from cli.main import build_parser
    args = build_parser().parse_args(['trajectory-predict', '--input', str(dataset / 'trajectory_004.npz'),
                                     '--checkpoint', str(checkpoint), '--output', str(tmp_path / 'cli.json')])
    assert args.func(args)['forecast']['kind'] == 'model_estimates'
    # Repeating the same seed preserves predictions and metrics.
    repeated = train(['--synthetic-root', str(dataset), '--case-id', 'TEST',
                      '--output', str(tmp_path / 'repeat.json'), '--model-output', str(tmp_path / 'repeat.pt'),
                      '--epochs', '2', '--hidden-size', '8', '--layers', '1', '--seed', '7',
                      '--input-frame', 'heading', '--threads', '1'])
    assert repeated['test']['gru']['overall'] == result['runs'][0]['test']['gru']['overall']


def test_single_flight_evaluation_does_not_claim_flight_confidence(dataset, tmp_path):
    # Longer NPZ permits nonempty validation/test chronological windows.
    root = tmp_path / 'long'
    generate_dataset(root, 1, 1, 1, duration_s=30., noise=clean_noise())
    result = train(['--input', str(root / 'trajectory_000.npz'), '--case-id', 'SINGLE',
                    '--output', str(tmp_path / 'single.json'), '--model-output', str(tmp_path / 'single.pt'),
                    '--epochs', '1', '--hidden-size', '4', '--layers', '1', '--threads', '1'])
    assert not result['provenance']['data']['independent_flight_holdout']
    assert result['aggregate']['models']['gru']['flight_bootstrap_95_ci']['ade_m'] is None


def test_output_guards_and_legacy_checkpoint_rejection(dataset, tmp_path):
    with pytest.raises(ValueError, match='must not overwrite'):
        ensure_distinct_outputs([dataset / 'trajectory_000.npz'], [dataset / 'trajectory_000.npz'])
    with pytest.raises(ValueError, match='existing trajectory datasets'):
        generate_dataset(dataset)
    alias = tmp_path / 'evidence-alias.npz'
    alias.hardlink_to(dataset / 'trajectory_000.npz')
    with pytest.raises(ValueError, match='hard links'):
        ensure_distinct_outputs([alias], [dataset / 'trajectory_000.npz'])
    path = tmp_path / 'legacy.pt'
    torch.save({'model_state_dict': {}}, path)
    with pytest.raises(ValueError, match='Retrain'):
        TrajectoryPredictor(path)


def test_grouped_platform_validation_and_source_integrity(dataset):
    from ml.trajectory_provenance import verify_source_hashes
    path = dataset / 'manifest.json'
    with pytest.raises(ValueError, match='crosses'):
        read_manifest(path, holdout_group='platform')
    entries = read_manifest(path)
    verify_source_hashes({'sources': entries})
    changed = Path(entries[0]['path'])
    changed.write_bytes(changed.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='Source changed'):
        verify_source_hashes({'sources': entries})
