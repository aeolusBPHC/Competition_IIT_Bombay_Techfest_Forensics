import argparse
import hashlib
import json
import runpy
from pathlib import Path

import pytest

from cli.pipeline import process_evidence

ROOT = Path(__file__).resolve().parents[1]


def arguments(source, output=None, **kwargs):
    return argparse.Namespace(input=str(source), case='TEST-PIPELINE',
                              output=str(output) if output else None,
                              media=None, portable_media=False, checkpoint=None, **kwargs)


def test_process_acquires_analyzes_and_renders_media(tmp_path, monkeypatch):
    from PIL import Image
    build = runpy.run_path(str(ROOT / 'tests/fixtures/create_ardupilot_forensics_fixture.py'))['build_fixture']
    source = tmp_path / 'log.bin'
    source.write_bytes(build())
    before = source.read_bytes()
    media = tmp_path / 'photo.png'
    Image.new('RGB', (16, 16), 'blue').save(media)
    monkeypatch.chdir(tmp_path)
    args = arguments(source, tmp_path / 'result')
    args.media, args.portable_media = str(media), True
    result = process_evidence(args)
    assert source.read_bytes() == before
    acquired = Path(result['acquired_log'])
    assert acquired.read_bytes() == before
    normalized = json.loads(Path(result['artifacts']['normalized_report']).read_text())
    assert normalized['record_counts']['gps'] == 2
    html = Path(result['artifacts']['html_report']).read_text()
    assert 'Evidence Gallery' in html and 'photo.png' in html
    assert list((tmp_path / 'result/forensic_report_assets').glob('*.png'))
    assert (acquired.parent.parent / 'chain_of_custody.json').is_file()
    assert result['log_integrity_reverified']
    for relative, digest in result['sha256'].items():
        assert hashlib.sha256((tmp_path / 'result' / relative).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        process_evidence(args)


def test_process_rejects_unsupported_without_acquisition(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / 'invalid.txt'
    source.write_text('not a flight log')
    with pytest.raises(ValueError, match='Unsupported'):
        process_evidence(arguments(source))
    assert not (tmp_path / 'repository').exists()


def test_process_identifies_lfs_pointer(tmp_path):
    source = tmp_path / 'log.ulg'
    source.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 123\n')
    with pytest.raises(ValueError, match='Git LFS pointer'):
        process_evidence(arguments(source))


def test_repeated_acquisitions_do_not_overwrite(tmp_path, monkeypatch):
    from acquisition.acquire import acquire_evidence
    monkeypatch.chdir(tmp_path)
    source = tmp_path / 'log.bin'
    source.write_bytes(b'first')
    first = acquire_evidence(source, 'CASE-TEST')
    source.write_bytes(b'second')
    second = acquire_evidence(source, 'CASE-TEST')
    assert first['evidence_id'] != second['evidence_id']
    assert Path(first['acquired_file']).read_bytes() == b'first'


def test_gallery_resolves_recovered_image_and_rejects_escape(tmp_path):
    from reporting.evidence_gallery import _resolve_media_path
    recovered = tmp_path / 'recovered'
    (recovered / 'p2048_all').mkdir(parents=True)
    photo = recovered / 'p2048_all/photo.jpg'
    photo.write_bytes(b'example')
    report = {'recovered_root': str(recovered)}
    assert _resolve_media_path(report, tmp_path / 'report.html',
                               'partition@2048/photo.jpg') == photo
    assert _resolve_media_path(report, tmp_path / 'report.html',
                               'partition@2048/../../outside.jpg') is None
