"""Report window metrics separately from uncertainty across independent flights."""
from __future__ import annotations

import numpy as np

from ml.trajectory_baseline import average_displacement_error, final_displacement_error


MODEL_NAMES = ("gru", "constant_velocity", "constant_acceleration")


def metric_block(predicted, actual):
    return {"ade_m": average_displacement_error(predicted, actual),
            "fde_m": final_displacement_error(predicted, actual)}


def classify_windows(X_original, feature_count=None):
    mean_speed = np.mean(X_original[..., 6], axis=1)
    stationary, moving = mean_speed < 0.1, mean_speed >= 0.5
    return {"stationary": stationary, "moving": moving,
            "intermediate": ~(stationary | moving)}


def evaluate_subset(predicted, actual, mask):
    count = int(np.sum(mask))
    return {"window_count": count,
            **(metric_block(predicted[mask], actual[mask]) if count
               else {"ade_m": None, "fde_m": None})}


def grouped_metrics(predicted, actual, groups):
    return {str(group): evaluate_subset(predicted, actual, groups == group)
            for group in sorted(set(groups.tolist()))}


def flight_macro(per_flight):
    return {metric: float(np.mean([value[metric] for value in per_flight.values()]))
            for metric in ("ade_m", "fde_m")}


def bootstrap_mean_ci(values, seed=42, samples=2000):
    """Resample independent flight means, not overlapping windows."""
    values = np.asarray(values, dtype=float)
    if len(values) < 2:
        return None
    rng = np.random.default_rng(seed)
    means = values[rng.integers(0, len(values), (samples, len(values)))].mean(axis=1)
    lower, upper = np.percentile(means, [2.5, 97.5])
    return {"lower": float(lower), "upper": float(upper)}


def evaluate_predictions(predicted, actual, block):
    per_flight = grouped_metrics(predicted, actual, block["trajectory_ids"])
    return {
        "overall": metric_block(predicted, actual),
        "motion": {name: evaluate_subset(predicted, actual, mask)
                   for name, mask in classify_windows(block["X"]).items()},
        "horizon_ade_m": np.linalg.norm(predicted - actual, axis=-1).mean(axis=0).tolist(),
        "scenario": grouped_metrics(predicted, actual, block["scenarios"]),
        "platform": grouped_metrics(predicted, actual, block["platforms"]),
        "label_kind": grouped_metrics(predicted, actual, block["label_kinds"]),
        "per_flight": per_flight,
        "flight_macro": flight_macro(per_flight),
    }


def summarize_runs(runs, independent_flights):
    summary = {}
    for model in MODEL_NAMES:
        first = runs[0]["test"][model]["per_flight"]
        per_flight = {
            flight: {metric: float(np.mean([
                run["test"][model]["per_flight"][flight][metric] for run in runs
            ])) for metric in ("ade_m", "fde_m")} for flight in first
        }
        ci_available = independent_flights and len(first) >= 2
        summary[model] = {
            "flight_count": len(first), "seed_count": len(runs),
            "per_flight_mean_over_seeds": per_flight,
            "flight_macro_mean": flight_macro(per_flight),
            "seed_std_of_flight_macro": {
                metric: (float(np.std([run["test"][model]["flight_macro"][metric]
                                      for run in runs], ddof=1)) if len(runs) > 1 else None)
                for metric in ("ade_m", "fde_m")
            },
            "flight_bootstrap_95_ci": {
                metric: bootstrap_mean_ci([value[metric] for value in per_flight.values()])
                if ci_available else None for metric in ("ade_m", "fde_m")
            },
            "confidence_scope": (
                "Independent test flights; seed-averaged flight means; overlapping windows are not resampled."
                if ci_available else "Unavailable: at least two independent held-out flights are required."
            ),
        }
    paired = {}
    for baseline in MODEL_NAMES[1:]:
        paired[baseline] = {}
        for metric in ("ade_m", "fde_m"):
            learned = summary["gru"]["per_flight_mean_over_seeds"]
            physics = summary[baseline]["per_flight_mean_over_seeds"]
            differences = [learned[flight][metric] - physics[flight][metric] for flight in learned]
            paired[baseline][metric] = {
                "mean_gru_minus_baseline": float(np.mean(differences)),
                "flight_bootstrap_95_ci": (bootstrap_mean_ci(differences)
                                           if independent_flights else None),
            }
    return {"models": summary, "paired_comparison": paired,
            "negative_difference_favors": "gru", "seed_count": len(runs)}
