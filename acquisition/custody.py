"""SHA-256 custody chains anchored by a separately protected trusted checkpoint.

The checkpoint is an input to verification, never recovered from untrusted case
metadata. Protect it independently: a party able to replace both the case and
the trusted reference can forge a new, internally consistent history.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile


ZERO_HASH = "0" * 64
SCHEMA_VERSION = 1


class CustodyIntegrityError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"Non-finite JSON value: {value}")

    try:
        raw = Path(path).read_bytes()
        return raw, json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (OSError, ValueError, UnicodeError) as exc:
        raise CustodyIntegrityError("UNREADABLE_RECORD", f"{path}: {exc}") from exc


def _case_file(root, name):
    path = root / name
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CustodyIntegrityError("MISSING_CASE_FILE", f"Missing case file: {path}") from exc
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise CustodyIntegrityError("UNSAFE_CASE_PATH", f"Case file escapes the evidence directory: {path}")
    return resolved


def _external_checkpoint(root, checkpoint):
    path = Path(checkpoint).expanduser().resolve()
    if path.is_relative_to(root):
        raise CustodyIntegrityError("UNTRUSTED_CHECKPOINT_LOCATION",
                                   "The trusted checkpoint must be outside the evidence directory.")
    return path


def trust_directory(trust_dir=None):
    return Path(trust_dir or os.environ.get(
        "DRONE_FORENSICS_TRUST_DIR", "~/.local/share/drone-forensics/custody")).expanduser().resolve()


def checkpoint_for(case_directory, case_id, evidence_id, trust_dir=None):
    """Reserve a new reference location, separate from the whole case repository."""
    root = Path(case_directory).resolve()
    folder = trust_directory(trust_dir)
    if folder.is_relative_to(Path("repository/cases").resolve()) or folder.is_relative_to(root):
        raise ValueError("Trusted checkpoints must be stored outside repository/cases.")
    folder.mkdir(parents=True, mode=0o700, exist_ok=True)
    if os.name == "posix" and stat.S_IMODE(folder.stat().st_mode) & 0o022:
        raise ValueError("The trust directory must not be writable by group/other users.")
    name = _digest(_canonical({"case_id": case_id, "evidence_id": evidence_id})) + ".json"
    path = folder / name
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"A trusted checkpoint already exists: {path}")
    return path


@contextmanager
def _checkpoint_lock(path):
    lock = path.with_name(path.name + ".lock")
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CustodyIntegrityError("CHECKPOINT_BUSY", f"Another writer holds {lock}; retry after it finishes.") from exc
    try:
        os.close(descriptor)
        yield
    finally:
        lock.unlink()


def _atomic_write(path, content, *, replace=False):
    """Write complete bytes with owner-only permissions; new references never overwrite."""
    descriptor, temporary = tempfile.mkstemp(prefix=".custody-", dir=path.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temp, path)
        else:
            os.link(temp, path)  # Fails if the destination already exists.
    finally:
        temp.unlink(missing_ok=True)


def _chain_event(event, previous):
    result = dict(event)
    if "event_hash" in result or "previous_event_hash" in result:
        raise ValueError("New custody events must not supply their own chain hashes.")
    result["previous_event_hash"] = previous
    result["event_hash"] = _digest(_canonical(result))
    return result


def _check_chain(events, evidence_id):
    if not isinstance(events, list) or not events:
        raise CustodyIntegrityError("INVALID_LEDGER", "Custody must be a nonempty event list.")
    previous = ZERO_HASH
    for index, event in enumerate(events, 1):
        if not isinstance(event, dict) or type(event.get("event_id")) is not int or event["event_id"] != index:
            raise CustodyIntegrityError("INVALID_EVENT_ORDER", f"Invalid event sequence at position {index}.")
        if event.get("evidence_id") != evidence_id:
            raise CustodyIntegrityError("WRONG_EVIDENCE_ID", f"Wrong evidence ID at event {index}.")
        if event.get("previous_event_hash") != previous:
            raise CustodyIntegrityError("BROKEN_CHAIN", f"Previous-event hash differs at event {index}.")
        payload = {key: value for key, value in event.items() if key != "event_hash"}
        expected = _digest(_canonical(payload))
        if event.get("event_hash") != expected:
            raise CustodyIntegrityError("EDITED_EVENT", f"Event {index} no longer matches its hash.")
        previous = expected
    return previous


def _checkpoint(metadata, metadata_bytes, events, ledger_bytes):
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": metadata["case_id"], "evidence_id": metadata["evidence_id"],
        "evidence_filename": metadata["filename"],
        "evidence_sha256": metadata["forensic_copy_hash"],
        "metadata_sha256": _digest(metadata_bytes),
        "custody_sha256": _digest(ledger_bytes),
        "event_count": len(events), "head_hash": events[-1]["event_hash"],
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def seal_acquisition(case_directory, events, checkpoint, *, expected_metadata):
    """Seal a just-created acquisition; this is not retroactive proof for old cases."""
    root = Path(case_directory).resolve()
    trusted = _external_checkpoint(root, checkpoint)
    metadata_bytes, metadata = _json_bytes(_case_file(root, "metadata.json"))
    if _canonical(metadata) != _canonical(expected_metadata):
        raise CustodyIntegrityError("METADATA_CHANGED", "Metadata changed before its initial trusted checkpoint.")
    if (not metadata.get("integrity_verified") or
            metadata.get("original_hash") != metadata.get("forensic_copy_hash")):
        raise CustodyIntegrityError("ACQUISITION_MISMATCH", "Source and acquired-copy hashes do not match.")
    filename = metadata.get("filename")
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise CustodyIntegrityError("UNSAFE_CASE_PATH", "Invalid evidence filename.")
    copy = _case_file(root, Path("evidence") / filename)
    if _sha256_file(copy) != metadata["forensic_copy_hash"]:
        raise CustodyIntegrityError("EVIDENCE_CHANGED", "The acquired evidence changed before sealing.")
    ledger = root / "chain_of_custody.json"
    if ledger.exists() or ledger.is_symlink():
        raise FileExistsError("Refusing to replace an existing custody ledger.")
    chained = []
    for event in events:
        chained.append(_chain_event(event, chained[-1]["event_hash"] if chained else ZERO_HASH))
    _check_chain(chained, metadata["evidence_id"])
    ledger_bytes = _encoded(chained)
    with _checkpoint_lock(trusted):
        if trusted.exists() or trusted.is_symlink():
            raise FileExistsError(f"Refusing to replace trusted checkpoint: {trusted}")
        _atomic_write(ledger, ledger_bytes)
        _atomic_write(trusted, _encoded(_checkpoint(metadata, metadata_bytes, chained, ledger_bytes)))
    return verify_custody(root, trusted)


def _verified_snapshot(case_directory, checkpoint, expected_checkpoint_sha256=None):
    root = Path(case_directory).expanduser().resolve()
    trusted = _external_checkpoint(root, checkpoint)
    reference_bytes, reference = _json_bytes(trusted)
    if expected_checkpoint_sha256 is not None:
        if (not isinstance(expected_checkpoint_sha256, str) or
                not re.fullmatch(r"[0-9a-fA-F]{64}", expected_checkpoint_sha256)):
            raise CustodyIntegrityError("INVALID_CHECKPOINT_PIN", "Checkpoint SHA-256 must contain exactly 64 hexadecimal characters.")
        if _digest(reference_bytes) != expected_checkpoint_sha256.lower():
            raise CustodyIntegrityError("CHECKPOINT_CHANGED", "The trusted checkpoint differs from the pinned SHA-256.")
    required = {"case_id", "evidence_id", "evidence_filename", "evidence_sha256",
                "metadata_sha256", "custody_sha256", "event_count", "head_hash"}
    if (not isinstance(reference, dict) or type(reference.get("schema_version")) is not int or
            reference["schema_version"] != SCHEMA_VERSION or not required.issubset(reference)):
        raise CustodyIntegrityError("INVALID_CHECKPOINT", "Unsupported or incomplete trusted checkpoint.")
    metadata_path = _case_file(root, "metadata.json")
    metadata_bytes, metadata = _json_bytes(metadata_path)
    if _digest(metadata_bytes) != reference["metadata_sha256"]:
        raise CustodyIntegrityError("METADATA_CHANGED", "Acquisition metadata differs from its trusted reference.")
    if (not isinstance(metadata, dict) or metadata.get("case_id") != reference["case_id"] or
            metadata.get("evidence_id") != reference["evidence_id"]):
        raise CustodyIntegrityError("WRONG_CASE", "The checkpoint does not belong to this case/evidence.")
    filename = reference["evidence_filename"]
    if (not isinstance(filename, str) or not filename or filename in {".", ".."} or
            Path(filename).name != filename or "/" in filename or "\\" in filename):
        raise CustodyIntegrityError("UNSAFE_CASE_PATH", "Invalid evidence filename in checkpoint.")
    ledger_path = _case_file(root, "chain_of_custody.json")
    ledger_bytes, events = _json_bytes(ledger_path)
    head = _check_chain(events, reference["evidence_id"])
    if (type(reference["event_count"]) is not int or len(events) != reference["event_count"] or
            head != reference["head_hash"] or _digest(ledger_bytes) != reference["custody_sha256"]):
        raise CustodyIntegrityError("CHECKPOINT_MISMATCH", "The custody history differs from the trusted checkpoint.")
    evidence = _case_file(root, Path("evidence") / filename)
    actual = _sha256_file(evidence)
    if actual != reference["evidence_sha256"]:
        raise CustodyIntegrityError("EVIDENCE_CHANGED", "The acquired evidence differs from its trusted SHA-256.")
    state = {"status": "verified", "case_id": reference["case_id"], "evidence_id": reference["evidence_id"],
             "event_count": len(events), "head_hash": head, "evidence_sha256": actual,
             "checkpoint_sha256": _digest(reference_bytes), "checkpoint": str(trusted),
             "custody_ledger": str(ledger_path), "evidence_file": str(evidence)}
    return state, metadata_bytes, metadata, events


def verify_custody(case_directory, checkpoint, *, expected_checkpoint_sha256=None):
    """Read-only verification against the caller's independently trusted reference."""
    return _verified_snapshot(case_directory, checkpoint, expected_checkpoint_sha256)[0]


def append_custody_event(case_directory, checkpoint, *, event, operator, description, details=None):
    """Append through the trusted writer after verifying the existing case/history."""
    if not isinstance(event, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", event):
        raise ValueError("Event must be an uppercase identifier of at most 64 characters.")
    if not isinstance(operator, str) or not operator.strip() or not isinstance(description, str) or not description.strip():
        raise ValueError("Operator and description are required.")
    if details is not None and not isinstance(details, dict):
        raise ValueError("Event details must be a JSON object.")
    root = Path(case_directory).resolve()
    trusted = _external_checkpoint(root, checkpoint)
    with _checkpoint_lock(trusted):
        state, metadata_bytes, metadata, events = _verified_snapshot(root, trusted)
        ledger = _case_file(root, "chain_of_custody.json")
        payload = {"event_id": len(events) + 1, "event": event,
                   "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                   "operator": operator, "evidence_id": state["evidence_id"], "description": description}
        if details is not None:
            payload["details"] = details
        events.append(_chain_event(payload, state["head_hash"]))
        ledger_bytes = _encoded(events)
        _atomic_write(ledger, ledger_bytes, replace=True)
        _atomic_write(trusted, _encoded(_checkpoint(metadata, metadata_bytes, events, ledger_bytes)), replace=True)
        return verify_custody(root, trusted)
