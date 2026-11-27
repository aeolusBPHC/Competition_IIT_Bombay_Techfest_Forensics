"""Exercise the optional renderer against real PDF content, media and integrity."""
import base64
import hashlib
import runpy
from pathlib import Path

import pytest

from reporting.pdf_export import export_pdf


@pytest.fixture
def reader():
    pytest.importorskip("weasyprint")
    return pytest.importorskip("pypdf").PdfReader


def test_pdf_preserves_disclosures_tables_images_and_source(tmp_path, reader):
    from PIL import Image
    image = tmp_path / 'camera.png'
    Image.new('RGB', (32, 24), 'blue').save(image)
    encoded = base64.b64encode(image.read_bytes()).decode('ascii')
    source = tmp_path / 'report.html'
    rows = ''.join(f'<tr><td>Observation {i}</td><td>{i}</td></tr>' for i in range(130))
    source.write_text(
        '<html><body><h1>Forensic test report</h1>'
        '<details><summary>Evidence metadata</summary><p>Preserved camera serial ABC123</p></details>'
        '<details><summary>Model provenance</summary><p>Predictions are model estimates</p></details>'
        '<img src="camera.png"><img src="data:image/png;base64,' + encoded + '">'
        '<table><thead><tr><th>Recorded observations</th><th>Time</th></tr></thead><tbody>'
        + rows + '</tbody></table></body></html>')
    before = source.read_bytes()
    target = export_pdf(source, max_items=0)
    pdf = reader(target)
    text = '\n'.join(page.extract_text() for page in pdf.pages)
    assert 'Preserved camera serial ABC123' in text
    assert 'Predictions are model estimates' in text
    assert 'Observation 129' in text and len(pdf.pages) > 1
    assert 'Static PDF export' in text and 'Page 1 of' in text
    assert sum(len(page.images) for page in pdf.pages) >= 1
    assert source.read_bytes() == before
    assert (tmp_path / 'report.pdf.sha256').read_text().split()[0] == hashlib.sha256(target.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        export_pdf(source)


def test_pdf_refuses_to_overwrite_existing_files(tmp_path):
    source = tmp_path / 'report.html'
    source.write_text('<h1>Keep this</h1>')
    target = tmp_path / 'existing.pdf'
    target.write_bytes(b'original evidence')
    with pytest.raises(FileExistsError):
        export_pdf(source, target)
    assert target.read_bytes() == b'original evidence'
    target.unlink()
    sidecar = tmp_path / 'existing.pdf.sha256'
    sidecar.write_text('original checksum')
    with pytest.raises(FileExistsError):
        export_pdf(source, target)
    assert sidecar.read_text() == 'original checksum'


def test_missing_image_fails_without_creating_a_pdf(tmp_path, reader):
    source = tmp_path / 'report.html'
    source.write_text('<h1>Report</h1><img src="missing-plot.png">')
    with pytest.raises(RuntimeError, match='missing-plot'):
        export_pdf(source)
    assert not source.with_suffix('.pdf').exists()
    assert not source.with_suffix('.pdf.sha256').exists()


def test_large_table_preview_labels_omissions_and_preserves_html(tmp_path, reader):
    source = tmp_path / 'report.html'
    rows = ''.join(f'<tr><td>Recorded event {i:03d}</td></tr>' for i in range(110))
    source.write_text('<table><tbody>' + rows + '</tbody></table>')
    before = source.read_bytes()
    target = export_pdf(source)
    text = '\n'.join(page.extract_text() for page in reader(target).pages)
    assert 'Recorded event 099' in text
    assert 'Recorded event 109' not in text
    assert '100 of 110 items shown' in text and '10 omitted' in text
    assert 'complete HTML and JSON' in text
    assert source.read_bytes() == before


def test_pdf_pipeline_hashes_the_export_and_retains_media(tmp_path, monkeypatch, reader):
    from PIL import Image
    from cli.main import build_parser
    root = Path(__file__).resolve().parents[2]
    build = runpy.run_path(str(root / 'tests/fixtures/create_ardupilot_forensics_fixture.py'))['build_fixture']
    source = tmp_path / 'flight.bin'
    source.write_bytes(build())
    image = tmp_path / 'camera.png'
    Image.new('RGB', (16, 16), 'red').save(image)
    monkeypatch.chdir(tmp_path)
    args = build_parser().parse_args(['process', '--input', str(source), '--pdf',
                                     '--media', str(image), '--portable-media',
                                     '--output', str(tmp_path / 'results')])
    manifest = args.func(args)
    target = Path(manifest['artifacts']['pdf_report'])
    pdf = reader(target)
    text = '\n'.join(page.extract_text() for page in pdf.pages)
    assert 'Evidence Gallery' in text and 'camera.png' in text
    assert any(page.images for page in pdf.pages)
    assert manifest['pdf_requested'] and manifest['log_integrity_reverified']
    assert target.name in manifest['sha256']
    assert target.name + '.sha256' in manifest['sha256']
    for relative, digest in manifest['sha256'].items():
        assert hashlib.sha256((target.parent / relative).read_bytes()).hexdigest() == digest


def test_pdf_failure_never_marks_run_complete(tmp_path, monkeypatch):
    from cli.main import build_parser
    import reporting.pdf_export as exporter
    root = Path(__file__).resolve().parents[2]
    build = runpy.run_path(str(root / 'tests/fixtures/create_ardupilot_forensics_fixture.py'))['build_fixture']
    source = tmp_path / 'flight.bin'
    source.write_bytes(build())
    monkeypatch.chdir(tmp_path)
    # Isolate renderer failure from an installation check.
    monkeypatch.setattr(exporter, 'check_pdf_support', lambda: None)
    def fail(*args):
        raise RuntimeError('PDF renderer failed')
    monkeypatch.setattr(exporter, 'export_pdf', fail)
    args = build_parser().parse_args(['process', '--input', str(source), '--pdf',
                                     '--output', str(tmp_path / 'results')])
    with pytest.raises(RuntimeError, match='PDF renderer failed'):
        args.func(args)
    assert not (tmp_path / 'results/run_manifest.json').exists()
