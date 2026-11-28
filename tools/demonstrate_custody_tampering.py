"""Demonstrate custody tamper detection on disposable copies of one acquisition."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import subprocess

from acquisition.acquire import acquire_evidence, calculate_sha256
from acquisition.custody import CustodyIntegrityError, append_custody_event, verify_custody


@contextmanager
def working_directory(path):
    before = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(before)


def rebuild(events):
    previous = "0" * 64
    for index, event in enumerate(events, 1):
        event.pop("event_hash", None)
        event["event_id"] = index
        event["previous_event_hash"] = previous
        previous = hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":"),
                                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        event["event_hash"] = previous
    return events


def demonstrate(output, source=None, trust_dir=None):
    output = Path(output).expanduser().resolve()
    supplied = Path(source).expanduser().resolve() if source else None
    if supplied and not supplied.is_file():
        raise ValueError(f"Input must be a local evidence file: {supplied}")
    trusted_store = (Path(trust_dir).expanduser().resolve() if trust_dir else
                     output.with_name(output.name + "_trusted-checkpoints"))
    if trusted_store.is_relative_to(output) or output.is_relative_to(trusted_store):
        raise ValueError("Demo trusted checkpoints must be separate from the demonstration output.")
    output.mkdir(parents=True, exist_ok=False)
    source_hash = calculate_sha256(supplied) if supplied else None
    local_source = output / "source" / (supplied.name if supplied else "generated_test_payload.bin")
    local_source.parent.mkdir()
    if supplied:
        shutil.copy2(supplied, local_source)
    else:
        local_source.write_bytes(bytes(range(256)) * 128)
    with working_directory(output):
        metadata = acquire_evidence(local_source, "TAMPER-DEMONSTRATION", operator="tamper-demo",
                                    trust_dir=trusted_store)
    case = Path(metadata["acquired_file"]).parent.parent
    checkpoint = Path(metadata["custody_checkpoint"])
    initial = verify_custody(case, checkpoint)
    results = [{"scenario": "unchanged acquisition", "expected": "verified", "observed": "verified",
                "passed": True, "events": initial["event_count"]}]
    state = append_custody_event(case, checkpoint, event="EVIDENCE_REVIEWED", operator="tamper-demo",
                                 description="Authorized review before creating disposable tamper copies.")
    results.append({"scenario": "authorized custody append", "expected": "verified", "observed": "verified",
                    "passed": True, "events": state["event_count"]})
    trusted_before = checkpoint.read_bytes()
    scenarios = ["evidence_byte_changed", "custody_entry_edited", "custody_entry_deleted",
                 "custody_entries_reordered", "custody_chain_rebuilt", "evidence_and_metadata_hashes_forged"]
    for attack in scenarios:
        target = output / "disposable-copies" / attack / case.name
        shutil.copytree(case, target)
        evidence = target / "evidence" / metadata["filename"]
        ledger = target / "chain_of_custody.json"
        events = json.loads(ledger.read_text())
        if attack in {"evidence_byte_changed", "evidence_and_metadata_hashes_forged"}:
            raw = bytearray(evidence.read_bytes())
            if raw:
                raw[len(raw) // 2] ^= 1
            else:
                raw.append(1)
            evidence.write_bytes(raw)
        if attack == "custody_entry_edited":
            events[1]["operator"] = "unauthorized-change"
        elif attack == "custody_entry_deleted":
            events.pop()
        elif attack == "custody_entries_reordered":
            events[1], events[2] = events[2], events[1]
        elif attack == "custody_chain_rebuilt":
            events[0]["description"] = "forged history, with all local chain hashes recalculated"
            events = rebuild(events)
        elif attack == "evidence_and_metadata_hashes_forged":
            forged = calculate_sha256(evidence)
            path = target / "metadata.json"
            forged_metadata = json.loads(path.read_text())
            forged_metadata["original_hash"] = forged_metadata["forensic_copy_hash"] = forged
            path.write_text(json.dumps(forged_metadata, indent=2))
            events[1]["hash"] = forged
            events[3]["original_hash"] = events[3]["copy_hash"] = forged
            events = rebuild(events)
        if attack != "evidence_byte_changed":
            ledger.write_text(json.dumps(events, indent=2) + "\n")
        try:
            verify_custody(target, checkpoint)
            result = {"scenario": attack, "expected": "rejected", "observed": "verified", "passed": False}
        except CustodyIntegrityError as exc:
            result = {"scenario": attack, "expected": "rejected", "observed": "rejected", "passed": True,
                      "reason_code": exc.code, "reason": str(exc)}
        result["case_directory"] = str(target)
        results.append(result)
    assert checkpoint.read_bytes() == trusted_before
    assert verify_custody(case, checkpoint)["status"] == "verified"
    if supplied:
        assert calculate_sha256(supplied) == source_hash
    code_root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=code_root,
                                         text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    source_files = ["acquisition/acquire.py", "acquisition/custody.py", "cli/main.py",
                    "cli/pipeline.py", "tools/demonstrate_custody_tampering.py"]
    report = {"status": "passed" if all(row["passed"] for row in results) else "failed",
              "generated_utc": datetime.now(timezone.utc).isoformat(), "base_git_commit": commit,
              "source_code_sha256": {name: calculate_sha256(code_root / name) for name in source_files},
              "input_kind": "supplied file; disposable copies only" if supplied else "generated test fixture; not flight evidence",
              "input_file": str(supplied) if supplied else None,
              "source_sha256": source_hash or calculate_sha256(local_source),
              "supplied_input_unchanged": True if supplied else None,
              "baseline_case": str(case), "trusted_checkpoint": str(checkpoint),
              "trusted_checkpoint_sha256": calculate_sha256(checkpoint),
              "trusted_checkpoint_unchanged_during_attacks": True,
              "positive_controls_verified": 2,
              "tampering_detected": sum(row["passed"] for row in results[2:]), "scenarios": results,
              "trust_boundary": "The verifier must use the original independently protected checkpoint. Replacing both case and trusted reference is outside this guarantee. Operator labels and host clock are not authenticated; this does not enforce write blocking."}
    json_path = output / "tamper_demo_report.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    rows = "".join("<tr><td>" + html.escape(row["scenario"]) + "</td><td>" + row["expected"]
                   + "</td><td>" + row["observed"] + "</td><td>" + html.escape(row.get("reason_code", "control"))
                   + "</td></tr>" for row in results)
    page = ("<!doctype html><html lang=en><meta charset=utf-8><title>Custody tamper demonstration</title>"
            "<style>body{font:16px Arial;max-width:1100px;margin:35px auto;padding:20px;color:#182534}"
            "table{width:100%;border-collapse:collapse}td,th{padding:10px;border:1px solid #ccd4dd;text-align:left}"
            ".notice{background:#fff8e8;padding:15px}code{overflow-wrap:anywhere}</style>"
            "<h1>Custody tamper demonstration</h1><p><strong>Status: " + report["status"].upper() + "</strong> · "
            "2 positive controls · " + str(report["tampering_detected"]) + "/6 tamper scenarios detected.</p>"
            "<p>Input: " + html.escape(report["input_kind"]) + "</p><p>Source SHA-256: <code>"
            + report["source_sha256"] + "</code></p><table><thead><tr><th>Scenario</th><th>Expected</th>"
            "<th>Observed</th><th>Reason</th></tr></thead><tbody>" + rows + "</tbody></table>"
            "<p class=notice>" + html.escape(report["trust_boundary"]) + "</p>"
            "<p><a href=tamper_demo_report.json>Machine-readable results and code hashes</a></p></html>")
    html_path = output / "tamper_demo_report.html"
    html_path.write_text(page, encoding="utf-8")
    for path in [json_path, html_path]:
        Path(str(path) + ".sha256").write_text(f"{calculate_sha256(path)}  {path.name}\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New directory for the demonstration")
    parser.add_argument("--input", help="Optional existing evidence file; the original is never modified")
    parser.add_argument("--trust-dir", help="Separate protected checkpoint store; defaults to a sibling of --output")
    args = parser.parse_args(argv)
    result = demonstrate(args.output, args.input, args.trust_dir)
    print(f"Tamper demonstration: {result['status']}; {result['tampering_detected']}/6 attacks detected")
    print(f"Open: {Path(args.output).resolve() / 'tamper_demo_report.html'}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
