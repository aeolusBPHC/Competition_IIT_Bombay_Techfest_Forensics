"""Load disjoint flights and build windows without crossing flight boundaries."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np

from ml.synthetic_trajectory_dataset import load_synthetic_trajectory
from ml.trajectory_dataset import chronological_split, chronological_windows, make_trajectory_windows
from ml.trajectory_features import build_trajectory_dataset
from ml.trajectory_provenance import file_hash


SPLITS = ("train", "validation", "test")


def load_trajectory(path):
    path = Path(path)
    if path.suffix.lower() == ".npz":
        return load_synthetic_trajectory(path)
    from platform_parsers.common.registry import ParserRegistry
    return build_trajectory_dataset(ParserRegistry().get_parser(path).parse())


def read_manifest(path, holdout_group=None):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for split in SPLITS:
        if not isinstance(data.get(split), list) or not data[split]:
            raise ValueError(f"Manifest must contain a nonempty {split} list.")
        for item in data[split]:
            if not isinstance(item, dict) or not item.get("flight_id") or not item.get("path"):
                raise ValueError("Each manifest flight needs path and flight_id.")
            if not isinstance(item["path"], str) or (
                item.get("platform") is not None and not isinstance(item["platform"], str)
            ):
                raise ValueError("Manifest paths and platform names must be strings.")
            source = (path.parent / item["path"]).resolve()
            entry = {**item, "path": str(source), "split": split, "sha256": file_hash(source)}
            entries.append(entry)
    validate_disjoint_flights(entries, holdout_group)
    return entries


def validate_disjoint_flights(entries, holdout_group=None):
    seen = {"flight_id": {}, "path": {}, "sha256": {}}
    groups = {}
    for entry in entries:
        for key, values in seen.items():
            value = entry[key]
            if not isinstance(value, str) or not value:
                raise ValueError(f"Flight {key} must be a nonempty string.")
            if value in values:
                raise ValueError(f"Duplicate {key} in {values[value]} and {entry['split']}; flights must be disjoint.")
            values[value] = entry["split"]
        if holdout_group:
            value = entry.get(holdout_group)
            if not isinstance(value, str) or not value:
                raise ValueError(f"Every flight needs a {holdout_group} for grouped holdout.")
            previous = groups.setdefault(value, entry["split"])
            if previous != entry["split"]:
                raise ValueError(f"{holdout_group} {value!r} crosses train/validation/test boundaries.")


def synthetic_entries(root):
    entries = []
    for path in sorted(Path(root).resolve().glob("trajectory_*.npz")):
        with np.load(path, allow_pickle=False) as data:
            split, flight_id = str(data["split"]), str(data["trajectory_id"])
        if split not in SPLITS:
            raise ValueError(f"Unknown synthetic split in {path}.")
        entries.append({"path": str(path), "split": split, "flight_id": flight_id,
                        "platform": "synthetic", "sha256": file_hash(path)})
    if any(not any(entry["split"] == split for entry in entries) for split in SPLITS):
        raise ValueError("Synthetic dataset must contain train, validation, and test flights.")
    validate_disjoint_flights(entries)
    return entries


def window_block(windows, dataset, entry):
    n = len(windows.X)
    return {
        "X": windows.X, "y": windows.y,
        "input_times": windows.input_timestamps, "target_times": windows.target_timestamps,
        "trajectory_ids": np.full(n, entry["flight_id"], dtype=object),
        "scenarios": np.full(n, dataset.scenario, dtype=object),
        "platforms": np.full(n, entry.get("platform", "unspecified"), dtype=object),
        "label_kinds": np.full(n, dataset.label_kind, dtype=object),
    }


def combine_blocks(blocks):
    if not blocks:
        raise ValueError("Each split must contain at least one usable flight.")
    result = {key: np.concatenate([block[key] for block in blocks]) for key in blocks[0]}
    result["trajectory_count"] = len(set(result["trajectory_ids"].tolist()))
    return result


def load_training_data(*, input_path=None, synthetic_root=None, manifest=None,
                       holdout_group=None, history_steps=20, prediction_steps=10, interval_s=0.1):
    if sum(value is not None for value in (input_path, synthetic_root, manifest)) != 1:
        raise ValueError("Supply exactly one of --input, --synthetic-root, or --manifest.")
    if holdout_group and not manifest:
        raise ValueError("--holdout-group requires --manifest.")
    settings = dict(history_steps=history_steps, prediction_steps=prediction_steps, interval_s=interval_s)
    if input_path:
        path = Path(input_path).resolve()
        entry = {"path": str(path), "sha256": file_hash(path), "flight_id": path.stem,
                 "split": "chronological"}
        dataset = load_trajectory(path)
        split_ranges = chronological_split(dataset)
        windows = {
            name: combine_blocks([window_block(
                chronological_windows(dataset, *bounds, **settings), dataset, entry,
            )]) for name, bounds in split_ranges.items()
        }
        entry["label_kind"] = dataset.label_kind
        entry["platform"] = dataset.source_platform
        entry["coordinate_origin"] = dataset.coordinate_origin
        return windows, {"mode": "single_flight_chronological", "sources": [entry],
                         "ranges_s": split_ranges, "independent_flight_holdout": False}
    manifest_hash = file_hash(manifest) if manifest else None
    entries = read_manifest(manifest, holdout_group) if manifest else synthetic_entries(synthetic_root)
    blocks = {name: [] for name in SPLITS}
    for entry in entries:
        dataset = load_trajectory(entry["path"])
        if (entry.get("platform") is not None
                and entry["platform"].casefold() != dataset.source_platform.casefold()):
            raise ValueError(f"Manifest platform for {entry['flight_id']} does not match parsed platform {dataset.source_platform}.")
        entry["platform"] = dataset.source_platform
        entry["label_kind"] = dataset.label_kind
        entry["scenario"] = dataset.scenario
        entry["trajectory_source"] = dataset.trajectory_source
        entry["coordinate_origin"] = dataset.coordinate_origin
        try:
            windows = make_trajectory_windows(dataset, **settings)
        except ValueError as error:
            raise ValueError(f"Flight {entry['flight_id']}: {error}") from error
        blocks[entry["split"]].append(window_block(windows, dataset, entry))
    validate_disjoint_flights(entries, holdout_group)
    return {name: combine_blocks(value) for name, value in blocks.items()}, {
        "mode": "manifest" if manifest else "synthetic_flight_holdout", "sources": entries,
        "holdout_group": holdout_group, "independent_flight_holdout": True,
        "manifest": ({"path": str(Path(manifest).resolve()), "sha256": manifest_hash}
                     if manifest else None),
    }
