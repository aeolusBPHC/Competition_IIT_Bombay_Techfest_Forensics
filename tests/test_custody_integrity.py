import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from acquisition.acquire import acquire_evidence
from acquisition.custody import (CustodyIntegrityError, append_custody_event,
                                  verify_custody)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def acquired(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "source.bin"
    source.write_bytes(bytes(range(256)) * 16)
    metadata = acquire_evidence(source, "CASE-CUSTODY", operator="examiner-1")
    case = Path(metadata["acquired_file"]).parent.parent
    return source, case, Path(metadata["custody_checkpoint"])


def read_ledger(case):
    return json.loads((case / "chain_of_custody.json").read_text())


def write_ledger(case, events):
    (case / "chain_of_custody.json").write_text(json.dumps(events, indent=2) + "\n")


def rebuild_chain(events):
    # Model an adversary who knows the public hashing algorithm, not a naive edit.
    previous = "0" * 64
    for index, event in enumerate(events, 1):
        event.pop("event_hash", None)
        event["event_id"] = index
        event["previous_event_hash"] = previous
        previous = hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":"),
                                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        event["event_hash"] = previous
    return events


def test_new_acquisition_is_anchored_and_verification_is_read_only(acquired):
    source, case, checkpoint = acquired
    assert not checkpoint.is_relative_to(case)
    before = {p: p.read_bytes() for p in [source, checkpoint, case / "metadata.json",
                                         case / "chain_of_custody.json", case / "evidence/source.bin"]}
    state = verify_custody(case, checkpoint)
    assert state["status"] == "verified" and state["event_count"] == 4
    assert state["evidence_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert all(p.read_bytes() == data for p, data in before.items())
    if os.name == "posix":
        assert checkpoint.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("attack", ["evidence_byte", "entry_edit", "entry_delete", "entry_reorder",
                                    "rebuilt_chain", "forged_evidence_and_metadata"])
def test_case_tampering_is_rejected_against_unchanged_reference(acquired, attack):
    source, case, checkpoint = acquired
    trusted = checkpoint.read_bytes()
    source_before = source.read_bytes()
    events = read_ledger(case)
    if attack in {"evidence_byte", "forged_evidence_and_metadata"}:
        evidence = case / "evidence/source.bin"
        raw = bytearray(evidence.read_bytes()); raw[10] ^= 1; evidence.write_bytes(raw)
    if attack == "entry_edit":
        events[1]["operator"] = "changed"
    elif attack == "entry_delete":
        events.pop()
    elif attack == "entry_reorder":
        events[1], events[2] = events[2], events[1]
    elif attack == "rebuilt_chain":
        events[0]["description"] = "rewritten history"
        events = rebuild_chain(events)
    elif attack == "forged_evidence_and_metadata":
        forged = hashlib.sha256((case / "evidence/source.bin").read_bytes()).hexdigest()
        metadata = json.loads((case / "metadata.json").read_text())
        metadata["original_hash"] = metadata["forensic_copy_hash"] = forged
        (case / "metadata.json").write_text(json.dumps(metadata))
        events[1]["hash"] = forged
        events[3]["original_hash"] = events[3]["copy_hash"] = forged
        events = rebuild_chain(events)
    if attack != "evidence_byte":
        write_ledger(case, events)
    with pytest.raises(CustodyIntegrityError):
        verify_custody(case, checkpoint)
    assert checkpoint.read_bytes() == trusted
    assert source.read_bytes() == source_before


def test_authorized_append_preserves_prefix_and_advances_trusted_checkpoint(acquired):
    _, case, checkpoint = acquired
    before = read_ledger(case)
    old_pin = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    state = append_custody_event(case, checkpoint, event="EVIDENCE_REVIEWED", operator="examiner-2",
                                 description="Reviewed the preserved copy.", details={"purpose": "review"})
    after = read_ledger(case)
    assert after[:-1] == before
    assert after[-1]["operator"] == "examiner-2"
    assert state["event_count"] == 5 and state["head_hash"] == after[-1]["event_hash"]
    assert verify_custody(case, checkpoint)["status"] == "verified"
    with pytest.raises(CustodyIntegrityError, match="CHECKPOINT_CHANGED"):
        verify_custody(case, checkpoint, expected_checkpoint_sha256=old_pin)
    assert verify_custody(case, checkpoint, expected_checkpoint_sha256=state["checkpoint_sha256"])


@pytest.mark.parametrize("pin", ["", "not-a-hash", "g" * 64])
def test_invalid_checkpoint_pin_cannot_silently_disable_pinning(acquired, pin):
    _, case, checkpoint = acquired
    with pytest.raises(CustodyIntegrityError, match="INVALID_CHECKPOINT_PIN"):
        verify_custody(case, checkpoint, expected_checkpoint_sha256=pin)


def test_append_cannot_bless_an_altered_history(acquired):
    _, case, checkpoint = acquired
    events = read_ledger(case)
    events[0]["operator"] = "forged"
    write_ledger(case, rebuild_chain(events))
    before = checkpoint.read_bytes()
    with pytest.raises(CustodyIntegrityError):
        append_custody_event(case, checkpoint, event="REVIEWED", operator="x", description="Review")
    assert checkpoint.read_bytes() == before


def test_verifier_refuses_missing_or_in_case_checkpoint(acquired):
    _, case, checkpoint = acquired
    embedded = case / "trusted.json"
    shutil.copy2(checkpoint, embedded)
    with pytest.raises(CustodyIntegrityError, match="UNTRUSTED_CHECKPOINT_LOCATION"):
        verify_custody(case, embedded)
    checkpoint.unlink()
    with pytest.raises(CustodyIntegrityError, match="UNREADABLE_RECORD"):
        verify_custody(case, checkpoint)
    assert not checkpoint.exists()


def test_trusted_reference_cannot_be_kept_under_case_repository(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "source.bin"; source.write_bytes(b"evidence")
    with pytest.raises(ValueError, match="outside repository/cases"):
        acquire_evidence(source, "TEST", trust_dir=tmp_path / "repository/cases/trusted")


def test_portable_case_verification_uses_local_evidence_not_metadata_absolute_path(acquired, tmp_path):
    _, case, checkpoint = acquired
    moved = tmp_path / "portable-copy"
    shutil.copytree(case, moved)
    assert verify_custody(moved, checkpoint)["status"] == "verified"
    (moved / "evidence/source.bin").write_bytes(b"modified portable copy")
    with pytest.raises(CustodyIntegrityError, match="EVIDENCE_CHANGED"):
        verify_custody(moved, checkpoint)
    assert verify_custody(case, checkpoint)["status"] == "verified"


def test_evidence_symlink_escape_is_rejected(acquired, tmp_path):
    _, case, checkpoint = acquired
    outside = tmp_path / "outside.bin"
    evidence = case / "evidence/source.bin"
    shutil.copy2(evidence, outside)
    evidence.unlink(); evidence.symlink_to(outside)
    with pytest.raises(CustodyIntegrityError, match="UNSAFE_CASE_PATH"):
        verify_custody(case, checkpoint)


def test_duplicate_json_keys_are_rejected(acquired):
    _, case, checkpoint = acquired
    metadata = case / "metadata.json"
    metadata.write_text('{"case_id":"a","case_id":"b"}')
    with pytest.raises(CustodyIntegrityError, match="Duplicate JSON key"):
        verify_custody(case, checkpoint)


def test_concurrent_writer_is_refused_without_changes(acquired):
    _, case, checkpoint = acquired
    lock = checkpoint.with_name(checkpoint.name + ".lock")
    lock.write_text("another writer")
    before = checkpoint.read_bytes(), (case / "chain_of_custody.json").read_bytes()
    with pytest.raises(CustodyIntegrityError, match="CHECKPOINT_BUSY"):
        append_custody_event(case, checkpoint, event="REVIEWED", operator="x", description="Review")
    assert before == (checkpoint.read_bytes(), (case / "chain_of_custody.json").read_bytes())
    assert lock.exists()


def test_interrupted_checkpoint_update_fails_closed(acquired, monkeypatch):
    import acquisition.custody as custody
    _, case, checkpoint = acquired
    real_write = custody._atomic_write
    trusted = checkpoint.read_bytes()
    def interrupted(path, data, **kwargs):
        if path == checkpoint:
            raise OSError("simulated storage failure")
        return real_write(path, data, **kwargs)
    monkeypatch.setattr(custody, "_atomic_write", interrupted)
    with pytest.raises(OSError, match="storage failure"):
        append_custody_event(case, checkpoint, event="REVIEWED", operator="x", description="Review")
    assert checkpoint.read_bytes() == trusted
    with pytest.raises(CustodyIntegrityError):
        verify_custody(case, checkpoint)


def test_initial_seal_rejects_changed_capture_metadata(tmp_path, monkeypatch):
    import acquisition.custody as custody
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "source.bin"; source.write_bytes(b"original")
    real_seal = custody.seal_acquisition
    def replaced_metadata(root, events, checkpoint, **kwargs):
        path = Path(root) / "metadata.json"
        metadata = json.loads(path.read_text())
        metadata["operator"] = "tampered before sealing"
        path.write_text(json.dumps(metadata))
        return real_seal(root, events, checkpoint, **kwargs)
    monkeypatch.setattr(custody, "seal_acquisition", replaced_metadata)
    with pytest.raises(CustodyIntegrityError, match="METADATA_CHANGED"):
        acquire_evidence(source, "TEST")
    assert not list((tmp_path / "trusted-checkpoints").glob("*.json"))


def test_cli_exit_status_detects_tampering(acquired):
    _, case, checkpoint = acquired
    command = [sys.executable, "-m", "cli.main", "verify-custody", "--evidence-dir", str(case),
               "--checkpoint", str(checkpoint)]
    env = {**os.environ, "PYTHONPATH": ""}
    valid = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    assert valid.returncode == 0 and json.loads(valid.stdout)["status"] == "verified"
    (case / "evidence/source.bin").write_bytes(b"changed")
    invalid = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    assert invalid.returncode != 0 and "EVIDENCE_CHANGED" in invalid.stdout


def test_wrong_checkpoint_cannot_verify_another_acquisition(acquired):
    source, _, checkpoint = acquired
    second = acquire_evidence(source, "OTHER-CASE", operator="examiner")
    with pytest.raises(CustodyIntegrityError):
        verify_custody(Path(second["acquired_file"]).parent.parent, checkpoint)


def test_append_does_not_promote_metadata_changed_during_a_write(acquired, monkeypatch):
    import acquisition.custody as custody
    _, case, checkpoint = acquired
    trusted_evidence_hash = json.loads(checkpoint.read_text())["evidence_sha256"]
    real_write = custody._atomic_write
    changed = False
    def mutate_case(path, data, **kwargs):
        nonlocal changed
        if path.name == "chain_of_custody.json" and not changed:
            changed = True
            (case / "evidence/source.bin").write_bytes(b"substituted while recording")
            metadata = json.loads((case / "metadata.json").read_text())
            forged = hashlib.sha256(b"substituted while recording").hexdigest()
            metadata["original_hash"] = metadata["forensic_copy_hash"] = forged
            (case / "metadata.json").write_text(json.dumps(metadata))
        return real_write(path, data, **kwargs)
    monkeypatch.setattr(custody, "_atomic_write", mutate_case)
    with pytest.raises(CustodyIntegrityError):
        append_custody_event(case, checkpoint, event="REVIEWED", operator="x", description="Review")
    assert json.loads(checkpoint.read_text())["evidence_sha256"] == trusted_evidence_hash
    with pytest.raises(CustodyIntegrityError):
        verify_custody(case, checkpoint)


def test_pipeline_records_and_reverifies_sealed_media(tmp_path, monkeypatch):
    import runpy
    from PIL import Image
    from cli.main import build_parser
    monkeypatch.chdir(tmp_path)
    build = runpy.run_path(str(ROOT / "tests/fixtures/create_ardupilot_forensics_fixture.py"))["build_fixture"]
    log = tmp_path / "flight.bin"; log.write_bytes(build())
    photo = tmp_path / "photo.png"; Image.new("RGB", (12, 12), "blue").save(photo)
    args = build_parser().parse_args(["process", "--input", str(log), "--media", str(photo),
                                     "--output", str(tmp_path / "results")])
    manifest = args.func(args)
    state = manifest["custody"]
    assert state["status"] == "verified" and state["event_count"] == 7
    media = state["related_media"][0]
    assert media["status"] == "verified" and media["event_count"] == 5
    assert verify_custody(Path(state["custody_ledger"]).parent, state["checkpoint"])
    assert verify_custody(Path(media["custody_ledger"]).parent, media["checkpoint"])
    assert "custody_verification.json" in manifest["sha256"]


def test_pipeline_cannot_complete_if_media_changes_after_rendering(tmp_path, monkeypatch):
    import runpy
    from PIL import Image
    from cli.main import build_parser
    import reporting.normalized_report_generator as renderer
    monkeypatch.chdir(tmp_path)
    build = runpy.run_path(str(ROOT / "tests/fixtures/create_ardupilot_forensics_fixture.py"))["build_fixture"]
    log = tmp_path / "flight.bin"; log.write_bytes(build())
    photo = tmp_path / "photo.png"; Image.new("RGB", (12, 12), "blue").save(photo)
    real_render = renderer.generate_report
    def substitute_media(*args, **kwargs):
        result = real_render(*args, **kwargs)
        copies = list((tmp_path / "repository/cases").glob("*/*/evidence/photo.png"))
        assert len(copies) == 1
        copies[0].write_bytes(b"modified after rendering")
        return result
    monkeypatch.setattr(renderer, "generate_report", substitute_media)
    args = build_parser().parse_args(["process", "--input", str(log), "--media", str(photo),
                                     "--output", str(tmp_path / "results")])
    with pytest.raises(CustodyIntegrityError, match="EVIDENCE_CHANGED"):
        args.func(args)
    assert not (tmp_path / "results/run_manifest.json").exists()


def test_repeatable_demo_records_expected_rejections(tmp_path):
    from tools.demonstrate_custody_tampering import demonstrate
    result = demonstrate(tmp_path / "demo")
    assert result["status"] == "passed" and result["tampering_detected"] == 6
    assert result["input_kind"] == "generated test fixture; not flight evidence"
    assert result["trusted_checkpoint_unchanged_during_attacks"]
    assert not Path(result["trusted_checkpoint"]).is_relative_to(tmp_path / "demo")
    assert result["positive_controls_verified"] == 2
    assert all(scenario["passed"] for scenario in result["scenarios"])
