"""Verify that the optional PDF appendix retains the forecast/evidence boundary."""
import hashlib

import pytest

from ml.synthetic_trajectory import SensorNoise, generate_dataset
from ml.trajectory_gru_train import main as train
from ml.trajectory_inference import main as infer


def test_forecast_pdf_from_both_cli_entrypoints(tmp_path):
    pytest.importorskip('weasyprint')
    reader = pytest.importorskip('pypdf').PdfReader
    from cli.main import build_parser
    root = tmp_path / 'data'
    noise = SensorNoise(**{key: 0. for key in SensorNoise.__dataclass_fields__})
    generate_dataset(root, train_count=2, validation_count=2, test_count=2,
                     duration_s=8., seed=100, noise=noise)
    checkpoint = tmp_path / 'model.pt'
    train(['--manifest', str(root / 'manifest.json'), '--holdout-group', 'mission',
           '--case-id', 'PDF-TEST',
           '--output', str(tmp_path / 'benchmark.json'), '--model-output', str(checkpoint),
           '--epochs', '1', '--hidden-size', '4', '--layers', '1', '--threads', '1'])
    common = ['--input', str(root / 'trajectory_004.npz'), '--checkpoint', str(checkpoint),
              '--predictor', 'gru', '--pdf']
    # Direct inference module and central CLI must provide identical export behavior.
    for name in ['direct', 'central']:
        report = tmp_path / f'{name}.html'
        args = [*common, '--output', str(tmp_path / f'{name}.json'), '--report', str(report)]
        if name == 'direct':
            infer(args)
        else:
            parsed = build_parser().parse_args(['trajectory-predict', *args])
            parsed.func(parsed)
        target = report.with_suffix('.pdf')
        pdf = reader(target)
        text = ' '.join(' '.join(page.extract_text() for page in pdf.pages).split())
        assert 'model estimates, not recorded evidence' in text
        assert 'Source and model provenance' in text
        assert 'checkpoint' in text and 'gru' in text
        assert 'Forecast estimates' in text
        assert (tmp_path / f'{name}.pdf.sha256').read_text().split()[0] == hashlib.sha256(target.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='requires --report'):
        infer([*common, '--output', str(tmp_path / 'invalid.json')])
    assert not (tmp_path / 'invalid.json').exists()
