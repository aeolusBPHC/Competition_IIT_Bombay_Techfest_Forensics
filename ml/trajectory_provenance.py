from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def runtime_provenance():
    versions = {"python": platform.python_version()}
    for package in ("numpy", "torch", "pyulog", "pymavlink"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
            check=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        revision = None
    sources = {}
    for folder in ("ml", "platform_parsers", "cli", "reporting"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            sources[str(path.relative_to(ROOT))] = file_hash(path)
    return {"dependencies": versions, "git_revision": revision, "source_sha256": sources}


def ensure_distinct_outputs(outputs, inputs=()):
    """An output must never overwrite evidence, a dataset, or another output."""
    outputs = [Path(path).resolve() for path in outputs if path is not None]
    inputs = {Path(path).resolve() for path in inputs if path is not None}
    if len(set(outputs)) != len(outputs) or any(path in inputs for path in outputs):
        raise ValueError("Output paths must be distinct and must not overwrite input files.")
    # resolve() handles symlinks; inode identity also catches hard links.
    existing = {path: (path.stat().st_dev, path.stat().st_ino)
                for path in [*outputs, *inputs] if path.exists()}
    for index, path in enumerate(outputs):
        if path in existing and any(existing.get(other) == existing[path]
                                    for other in [*outputs[index + 1:], *inputs]):
            raise ValueError("Output paths must be distinct and must not overwrite input files through hard links.")


def verify_source_hashes(data):
    sources = list(data["sources"])
    if data.get("manifest"):
        sources.append(data["manifest"])
    for entry in sources:
        if file_hash(entry["path"]) != entry["sha256"]:
            raise ValueError(f"Source changed during the experiment: {entry['path']}")


def write_json(path, value):
    import json
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
