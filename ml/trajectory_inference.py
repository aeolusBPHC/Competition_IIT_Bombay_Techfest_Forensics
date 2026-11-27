"""Forecast from a saved checkpoint, keeping observations and estimates separate."""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import torch

from ml.trajectory_baseline import constant_acceleration_predict, constant_velocity_predict
from ml.trajectory_data import load_trajectory
from ml.trajectory_dataset import latest_history
from ml.trajectory_features import FEATURE_CONTRACT_VERSION, FEATURE_NAMES
from ml.trajectory_gru import TrajectoryGRU
from ml.trajectory_preprocessing import Standardizer, WindowTransform
from ml.trajectory_provenance import ensure_distinct_outputs, file_hash, runtime_provenance, write_json


class TrajectoryPredictor:
    def __init__(self, checkpoint_path, device="cpu"):
        self.path = Path(checkpoint_path)
        self.device = torch.device(device)
        checkpoint = torch.load(self.path, map_location="cpu", weights_only=True)
        if (checkpoint.get("checkpoint_schema_version") != 2
                or checkpoint.get("feature_contract_version") != FEATURE_CONTRACT_VERSION
                or checkpoint.get("coordinate_frame") != "ENU"
                or checkpoint.get("feature_names") != FEATURE_NAMES):
            raise ValueError("Incompatible checkpoint contract. Retrain with the current ENU pipeline; legacy checkpoints cannot be relabeled safely.")
        self.checkpoint = checkpoint
        self.history_steps = checkpoint["history_steps"]
        self.interval_s = checkpoint["interval_s"]
        self.prediction_steps = checkpoint["model_config"]["prediction_steps"]
        if self.history_steps < 2 or self.prediction_steps < 1:
            raise ValueError("Invalid checkpoint sequence lengths.")
        self.transform = WindowTransform(**checkpoint["preprocessing"])
        if self.transform.interval_s != self.interval_s:
            raise ValueError("Checkpoint sampling and preprocessing intervals differ.")
        self.feature_scaler = Standardizer.from_dict(checkpoint["feature_scaler"])
        self.target_scaler = Standardizer.from_dict(checkpoint["target_scaler"])
        if len(self.feature_scaler.mean_) != len(FEATURE_NAMES) or len(self.target_scaler.mean_) != 3:
            raise ValueError("Checkpoint scaler dimensions do not match the feature contract.")
        self.model = TrajectoryGRU(**checkpoint["model_config"]).to(self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()

    @torch.no_grad()
    def predict(self, X, predictor="selected", feature_names=None):
        if feature_names is not None and list(feature_names) != FEATURE_NAMES:
            raise ValueError("Input feature order does not match the checkpoint.")
        X = np.asarray(X, dtype=float)
        if (X.ndim != 3 or X.shape[1:] != (self.history_steps, len(FEATURE_NAMES))
                or not len(X) or not np.all(np.isfinite(X))):
            raise ValueError("Prediction requires finite histories matching the checkpoint shape.")
        if predictor == "selected":
            predictor = self.checkpoint["recommended_predictor"]
        if predictor == "constant_velocity":
            predicted = constant_velocity_predict(X, self.prediction_steps, self.interval_s)
        elif predictor == "constant_acceleration":
            predicted = constant_acceleration_predict(X, self.prediction_steps, self.interval_s)
        elif predictor == "gru":
            scaled = self.feature_scaler.transform(self.transform.features(X))
            tensor = torch.from_numpy(scaled.astype(np.float32)).to(self.device)
            learned = self.model(tensor).cpu().numpy()
            predicted = self.transform.absolute(self.target_scaler.inverse_transform(learned), X)
        else:
            raise ValueError(f"Unknown predictor: {predictor}")
        if not np.all(np.isfinite(predicted)):
            raise ValueError("Non-finite model forecast.")
        return predicted


def add_arguments(parser):
    parser.add_argument("--input", required=True, help="Flight log or synthetic NPZ observations.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True, help="Forecast JSON, stored separately from source evidence.")
    parser.add_argument("--report", help="Optional HTML forecast report.")
    parser.add_argument("--pdf", action="store_true", help="Also export --report as PDF (requires --report).")
    parser.add_argument("--case-id")
    parser.add_argument("--at-time", type=float, help="Forecast using only observations up to this source timestamp.")
    parser.add_argument("--predictor", choices=("selected", "gru", "constant_velocity", "constant_acceleration"),
                        default="selected", help="Default uses the predictor chosen on validation flights.")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    return parser


def run(args):
    pdf_requested = getattr(args, "pdf", False)
    pdf = None
    if pdf_requested:
        if not args.report:
            raise ValueError("--pdf requires --report for the HTML forecast appendix")
        from reporting.pdf_export import check_pdf_support
        check_pdf_support()
        pdf = Path(args.report).with_suffix(".pdf")
        if pdf.exists() or Path(str(pdf) + ".sha256").exists():
            raise FileExistsError(f"PDF or checksum already exists; choose a new --report: {pdf}")
    ensure_distinct_outputs([args.output, args.report, pdf,
                             str(pdf) + ".sha256" if pdf else None], [args.input, args.checkpoint])
    predictor = TrajectoryPredictor(args.checkpoint, args.device)
    dataset = load_trajectory(args.input)
    if args.at_time is not None:
        if (not np.isfinite(args.at_time) or args.at_time > dataset.timestamps[-1]
                or args.at_time < dataset.timestamps[0]):
            raise ValueError("--at-time must lie within the recorded trajectory.")
        dataset = dataset.subset(np.flatnonzero(dataset.timestamps <= args.at_time))
    X, observed_times = latest_history(dataset, predictor.history_steps, predictor.interval_s)
    predicted = predictor.predict(X, args.predictor, dataset.feature_names)[0]
    selected = (predictor.checkpoint["recommended_predictor"]
                if args.predictor == "selected" else args.predictor)
    forecast_times = observed_times[-1] + np.arange(1, predictor.prediction_steps + 1) * predictor.interval_s
    result = {
        "schema_version": "2.0", "case_id": args.case_id,
        "artifact_type": "trajectory_forecast", "coordinate_frame": "ENU",
        "axes": {"x": "east", "y": "north", "z": "up"}, "position_units": "m",
        "timestamp_domain": "source log seconds; not necessarily UTC",
        "source": {"path": str(Path(args.input).resolve()), "sha256": file_hash(args.input),
                   "trajectory_source": dataset.trajectory_source,
                   "coordinate_origin": dataset.coordinate_origin,
                   "label_kind": dataset.label_kind},
        "model": {"checkpoint": str(predictor.path.resolve()), "sha256": file_hash(predictor.path),
                  "predictor": selected, "seed": predictor.checkpoint["seed"],
                  "selection_rule": predictor.checkpoint["selection_rule"],
                  "feature_contract_version": FEATURE_CONTRACT_VERSION},
        "observed_history": {"kind": "causally_resampled_observations",
                             "timestamps_s": observed_times.tolist(),
                             "positions_m": X[0, :, :3].tolist(),
                             "velocities_m_s": X[0, :, 3:6].tolist()},
        "forecast": {"kind": "model_estimates", "recorded_evidence": False,
                     "cutoff_timestamp_s": float(observed_times[-1]),
                     "timestamps_s": forecast_times.tolist(), "positions_m": predicted.tolist(),
                     "prediction_interval": None,
                     "uncertainty_note": "No calibrated prediction interval. Flight-level benchmark confidence intervals describe aggregate error, not the certainty of this path."},
        "provenance": {"inference_runtime": runtime_provenance(),
                       "training": predictor.checkpoint["provenance"]},
    }
    write_json(args.output, result)
    if args.report:
        from reporting.trajectory_report import generate_trajectory_report
        generate_trajectory_report(result, args.report)
        if pdf_requested:
            from reporting.pdf_export import export_pdf
            export_pdf(args.report, pdf)
            print(f"Forecast PDF: {pdf}")
    print(f"Saved {selected} forecast to {args.output}")
    return result


def main(argv=None):
    return run(add_arguments(argparse.ArgumentParser(description=__doc__)).parse_args(argv))


if __name__ == "__main__":
    main()
