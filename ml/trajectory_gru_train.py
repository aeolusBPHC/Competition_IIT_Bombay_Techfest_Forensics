"""Train, validate, and benchmark trajectory models with a reproducible contract."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import random

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from ml.trajectory_baseline import constant_acceleration_predict, constant_velocity_predict
from ml.trajectory_data import load_training_data, combine_blocks, window_block
from ml.trajectory_dataset import chronological_split, chronological_windows, make_trajectory_windows
from ml.trajectory_evaluation import (
    MODEL_NAMES, classify_windows, evaluate_predictions, evaluate_subset, metric_block,
    grouped_metrics, summarize_runs,
)
from ml.trajectory_features import COORDINATE_FRAME, FEATURE_CONTRACT_VERSION, FEATURE_NAMES
from ml.trajectory_gru import TrajectoryGRU
from ml.trajectory_preprocessing import Standardizer, WindowTransform
from ml.trajectory_provenance import ensure_distinct_outputs, file_hash, runtime_provenance, verify_source_hashes, write_json


SEED = 42


def set_seed(seed=SEED):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)


def parse_evidence(input_path):
    from platform_parsers.common.registry import ParserRegistry
    return ParserRegistry().get_parser(input_path).parse()


def build_synthetic_windows(root, split_name, history_steps, prediction_steps, interval_s, target_mode):
    from ml.synthetic_trajectory_dataset import load_synthetic_split
    return combine_blocks([
        window_block(make_trajectory_windows(dataset, history_steps, prediction_steps,
                                            interval_s, target_mode), dataset,
                     {"flight_id": dataset.trajectory_id, "platform": "synthetic"})
        for dataset in load_synthetic_split(root, split_name)
    ])


def synthetic_scenario_metrics(predicted, actual, scenarios):
    return grouped_metrics(predicted, actual, scenarios)


def torch_loader(X, y, batch_size, shuffle):
    return DataLoader(TensorDataset(torch.from_numpy(X.astype(np.float32)),
                                   torch.from_numpy(y.astype(np.float32))),
                      batch_size=batch_size, shuffle=shuffle, num_workers=0)


def train_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total, count = 0.0, 0
    for X, y in loader:
        X, y = X.to(device), y.to(device)
        optimizer.zero_grad()
        loss = criterion(model(X), y)
        if not torch.isfinite(loss):
            raise ValueError("Non-finite training loss; check data and normalization.")
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total += loss.item() * len(X)
        count += len(X)
    return total / count


@torch.no_grad()
def validation_loss(model, loader, criterion, device):
    model.eval()
    total, count = 0.0, 0
    for X, y in loader:
        loss = criterion(model(X.to(device)), y.to(device))
        total += loss.item() * len(X)
        count += len(X)
    return total / count


@torch.no_grad()
def predict_model(model, X, device, batch_size=512):
    model.eval()
    outputs = []
    for start in range(0, len(X), batch_size):
        values = torch.from_numpy(X[start:start + batch_size].astype(np.float32)).to(device)
        outputs.append(model(values).cpu().numpy())
    return np.concatenate(outputs)


def reconstruct_absolute_positions(displacements, X):
    return displacements + X[:, -1:, :3]


def horizon_errors(predicted, actual):
    return np.linalg.norm(predicted - actual, axis=-1).mean(axis=0)


def checkpoint_path(path, seed, first_seed):
    path = Path(path)
    return path if seed == first_seed else path.with_name(f"{path.stem}.seed-{seed}{path.suffix}")


def train_run(args, windows, seed, device, provenance, model_path):
    set_seed(seed)
    transform = WindowTransform(args.input_frame, args.target_mode, args.interval)
    feature_scaler, target_scaler = Standardizer(), Standardizer()
    train_X = transform.features(windows["train"]["X"])
    train_y = transform.targets(windows["train"]["y"], windows["train"]["X"])
    feature_scaler.fit(train_X)
    target_scaler.fit(train_y)
    scaled_X = {name: feature_scaler.transform(transform.features(block["X"]))
                for name, block in windows.items()}
    train_loader = torch_loader(feature_scaler.transform(train_X), target_scaler.transform(train_y),
                                args.batch_size, True)
    val_y = target_scaler.transform(transform.targets(windows["validation"]["y"],
                                                     windows["validation"]["X"]))
    val_loader = torch_loader(scaled_X["validation"], val_y, args.batch_size, False)
    model_config = {"input_size": len(FEATURE_NAMES), "hidden_size": args.hidden_size,
                    "num_layers": args.layers, "prediction_steps": args.prediction_steps}
    model = TrajectoryGRU(**model_config).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    criterion = nn.MSELoss()
    best_loss, best_state, stale, best_epoch = float("inf"), None, 0, None
    history = []
    for epoch in range(1, args.epochs + 1):
        loss = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss = validation_loss(model, val_loader, criterion, device)
        if not np.isfinite(val_loss):
            raise ValueError("Non-finite validation loss.")
        history.append({"epoch": epoch, "train_loss": loss, "validation_loss": val_loss})
        print(f"Seed {seed}, epoch {epoch:03d}: train={loss:.6f}, validation={val_loss:.6f}", flush=True)
        if val_loss < best_loss:
            best_loss, best_epoch, stale = val_loss, epoch, 0
            best_state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
        else:
            stale += 1
        if stale >= args.patience:
            break
    model.load_state_dict(best_state)
    metrics = {}
    for split in ("validation", "test"):
        block = windows[split]
        learned = transform.absolute(target_scaler.inverse_transform(
            predict_model(model, scaled_X[split], device)), block["X"])
        predictions = {
            "gru": learned,
            "constant_velocity": constant_velocity_predict(block["X"], args.prediction_steps, args.interval),
            "constant_acceleration": constant_acceleration_predict(block["X"], args.prediction_steps, args.interval),
        }
        metrics[split] = {name: evaluate_predictions(value, block["y"], block)
                          for name, value in predictions.items()}
    # The inference default is selected on validation flights only. Test
    # results do not influence model, baseline, epoch or seed selection.
    recommended = min(MODEL_NAMES, key=lambda name: metrics["validation"][name]["flight_macro"]["ade_m"])
    checkpoint = {
        "checkpoint_schema_version": 2, "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "coordinate_frame": COORDINATE_FRAME, "feature_names": FEATURE_NAMES.copy(),
        "model_state_dict": best_state, "model_config": model_config,
        "history_steps": args.history_steps, "interval_s": args.interval,
        "preprocessing": asdict(transform), "feature_scaler": feature_scaler.to_dict(),
        "target_scaler": target_scaler.to_dict(), "seed": seed,
        "recommended_predictor": recommended,
        "selection_rule": "Lowest validation flight-macro ADE; never selected on test results.",
        "validation": metrics["validation"], "provenance": provenance,
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    verify_source_hashes(provenance["data"])
    torch.save(checkpoint, model_path)
    return {
        "seed": seed, "model_path": str(model_path), "model_sha256": file_hash(model_path),
        "recommended_predictor": recommended, "best_epoch": best_epoch,
        "best_validation_loss": best_loss,
        "training": {"epochs_requested": args.epochs, "epochs_completed": len(history),
                     "history": history}, **metrics,
    }


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="One real log or NPZ, split chronologically for exploration.")
    source.add_argument("--synthetic-root", help="Directory of NPZ flights with predefined splits.")
    source.add_argument("--manifest", help="JSON with disjoint train/validation/test flight lists.")
    parser.add_argument("--holdout-group", choices=("mission", "platform"),
                        help="Require this manifest group to be disjoint across all three splits.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", required=True, help="Benchmark JSON output.")
    parser.add_argument("--model-output", required=True, help="First seed checkpoint; extra seeds get suffixes.")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--patience", type=int, default=7)
    parser.add_argument("--history-steps", type=int, default=20)
    parser.add_argument("--prediction-steps", type=int, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--input-frame", choices=("global", "centered", "heading"), default="centered")
    parser.add_argument("--target-mode", choices=("absolute", "relative", "residual_velocity", "residual_acceleration"),
                        default="residual_velocity")
    seeds = parser.add_mutually_exclusive_group()
    seeds.add_argument("--seed", type=int, default=SEED)
    seeds.add_argument("--seeds", type=int, nargs="+", help="Repeat training on the same fixed splits.")
    parser.add_argument("--device", choices=("cpu", "cuda", "auto"), default="cpu")
    parser.add_argument("--threads", type=int, default=2)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    for name in ("epochs", "batch_size", "hidden_size", "layers", "patience", "prediction_steps", "threads"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive.")
    if args.history_steps < 2:
        parser.error("--history-steps must be at least two.")
    if not np.isfinite(args.learning_rate) or args.learning_rate <= 0:
        parser.error("--learning-rate must be positive and finite.")
    seeds = args.seeds if args.seeds is not None else [args.seed]
    if len(set(seeds)) != len(seeds) or any(seed < 0 or seed >= 2**32 for seed in seeds):
        parser.error("Seeds must be distinct integers in [0, 2**32).")
    WindowTransform(args.input_frame, args.target_mode, args.interval)
    torch.set_num_threads(args.threads)
    device_name = "cuda" if args.device == "auto" and torch.cuda.is_available() else args.device
    if device_name == "auto":
        device_name = "cpu"
    if device_name == "cuda":
        if not torch.cuda.is_available():
            parser.error("CUDA is not available; use --device cpu.")
        import os
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    device = torch.device(device_name)
    windows, data_provenance = load_training_data(
        input_path=args.input, synthetic_root=args.synthetic_root, manifest=args.manifest,
        holdout_group=args.holdout_group, history_steps=args.history_steps,
        prediction_steps=args.prediction_steps, interval_s=args.interval,
    )
    for name, block in windows.items():
        print(f"{name}: {block['trajectory_count']} flights, {len(block['X'])} windows", flush=True)
    model_paths = [checkpoint_path(args.model_output, seed, seeds[0]) for seed in seeds]
    ensure_distinct_outputs([args.output, *model_paths],
                            [entry["path"] for entry in data_provenance["sources"]] + [args.manifest])
    provenance = {**runtime_provenance(), "data": data_provenance, "arguments": vars(args),
                  "coordinate_frame": COORDINATE_FRAME, "feature_names": FEATURE_NAMES.copy(),
                  "feature_contract_version": FEATURE_CONTRACT_VERSION,
                  "resampling": {"inputs": "previous observation (causal)", "targets": "linear interpolation"},
                  "normalization_fit_on": "training_windows_only"}
    runs = [train_run(args, windows, seed, device, provenance, path)
            for seed, path in zip(seeds, model_paths)]
    result = {
        "schema_version": "2.0", "case_id": args.case_id, "device": str(device),
        "target_mode": args.target_mode, "input_frame": args.input_frame,
        "dataset_type": data_provenance["mode"], "provenance": provenance,
        "window_configuration": {"history_steps": args.history_steps,
                                 "history_span_s": (args.history_steps - 1) * args.interval,
                                 "prediction_steps": args.prediction_steps,
                                 "prediction_horizon_s": args.prediction_steps * args.interval,
                                 "interval_s": args.interval, "feature_count": len(FEATURE_NAMES)},
        "split_sizes": {name: {"trajectory_count": block["trajectory_count"], "window_count": len(block["X"])}
                        for name, block in windows.items()},
        "runs": runs, "test": runs[0]["test"],
        "aggregate": summarize_runs(runs, data_provenance["independent_flight_holdout"]),
        "interpretation": "Forecasts are model estimates. Real-log errors are against recorded estimator observations, not independent ground truth.",
    }
    write_json(args.output, result)
    for name, block in result["aggregate"]["models"].items():
        print(f"{name}: flight-macro ADE={block['flight_macro_mean']['ade_m']:.6f} m, "
              f"FDE={block['flight_macro_mean']['fde_m']:.6f} m")
    print(f"Saved benchmark: {args.output}")
    return result


if __name__ == "__main__":
    main()
