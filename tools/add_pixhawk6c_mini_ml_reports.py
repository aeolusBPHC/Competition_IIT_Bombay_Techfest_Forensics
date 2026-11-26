"""Add explicit GRU forecasts to an existing public-log report batch."""
import argparse
import base64
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import shutil
import sys
import traceback

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.trajectory_inference import TrajectoryPredictor, main as infer
from ml.trajectory_provenance import file_hash, write_json


def sidecar(path):
    path = Path(path)
    Path(str(path) + ".sha256").write_text(f"{file_hash(path)}  {path.name}\n")


def chart(result, output):
    history, forecast = result["observed_history"], result["forecast"]
    cutoff = forecast["cutoff_timestamp_s"]
    times = np.asarray(history["timestamps_s"]) - cutoff
    future_times = np.asarray(forecast["timestamps_s"]) - cutoff
    observed = np.asarray(history["positions_m"])
    predicted = np.asarray(forecast["positions_m"])
    assert predicted.shape == (10, 3) and np.all(np.isfinite(predicted))
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for axis, name, ax in zip(range(3), ("East", "North", "Up"), axes.flat):
        ax.plot(times, observed[:, axis], color="#1763ad", marker=".", label="Observed history")
        ax.plot(np.r_[0., future_times], np.r_[observed[-1, axis], predicted[:, axis]],
                color="#c34819", linestyle="--", marker=".", label="GRU estimate")
        ax.axvline(0., color="#667085", linewidth=1)
        ax.set(xlabel="Time relative to forecast cutoff (s)", ylabel=f"{name} position (m)")
        ax.grid(alpha=.25)
    axes[0, 0].legend()
    ax = axes[1, 1]
    ax.plot(observed[:, 0], observed[:, 1], color="#1763ad", marker=".", label="Observed history")
    ax.plot(np.r_[observed[-1, 0], predicted[:, 0]], np.r_[observed[-1, 1], predicted[:, 1]],
            color="#c34819", linestyle="--", marker=".", label="GRU estimate")
    ax.scatter(*observed[-1, :2], color="#172b4d", s=45, zorder=5, label="Forecast cutoff")
    ax.set(xlabel="East (m)", ylabel="North (m)", title="Local horizontal trajectory")
    ax.grid(alpha=.25)
    ax.legend()
    fig.suptitle("Observed trajectory and GRU forecast — local ENU coordinates", fontsize=14)
    fig.savefig(output, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()
    batch = args.batch.resolve()
    rows = json.loads((batch / "batch_results.json").read_text())
    assert len(rows) == 7 and all(row["status"] == "passed" for row in rows)
    checkpoint = args.checkpoint.resolve()
    model_digest = file_hash(checkpoint)
    model_dir = batch / "models"
    model_dir.mkdir(exist_ok=True)
    snapshot = model_dir / "gru_seed42.pt"
    if snapshot.exists():
        assert file_hash(snapshot) == model_digest
    else:
        shutil.copy2(checkpoint, snapshot)
    assert file_hash(snapshot) == model_digest
    sidecar(snapshot)
    predictor = TrajectoryPredictor(snapshot)
    training_sources = predictor.checkpoint["provenance"]["data"]["sources"]
    assert not ({row["sha256"] for row in rows} & {entry["sha256"] for entry in training_sources})
    ml_results = []
    for row in rows:
        folder = batch / row["slug"]
        manifest_path = folder / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        acquired = Path(manifest["acquired_log"])
        assert file_hash(acquired) == row["sha256"] == file_hash(row["path"])
        print(f"FORECAST {row['slug']}", flush=True)
        info = {"slug": row["slug"], "predictor": "gru", "checkpoint_sha256": model_digest,
                "automatic_checkpoint_choice": predictor.checkpoint["recommended_predictor"],
                "status": "failed"}
        log_path = folder / "ml_processing.log"
        try:
            output_json, output_html = folder / "ml_predictions.json", folder / "ml_report.html"
            arguments = ["--input", str(acquired), "--checkpoint", str(snapshot),
                         "--predictor", "gru", "--case-id", manifest["case_id"],
                         "--output", str(output_json), "--report", str(output_html)]
            cutoff_note = "Uses the latest continuous valid history in the log."
            try:
                result = infer(arguments)
            except ValueError as error:
                if "continuous history" not in str(error):
                    raise
                # Never bridge invalid estimates, gaps or resets to fabricate a history.
                from ml.trajectory_data import load_trajectory
                from ml.trajectory_dataset import _continuous_chunks
                data = load_trajectory(acquired)
                chunks = _continuous_chunks(data, predictor.interval_s)
                minimum = (predictor.history_steps - 1) * predictor.interval_s
                usable = [indices for indices in chunks
                          if data.timestamps[indices[-1]] - data.timestamps[indices[0]] >= minimum - 1e-9]
                if not usable:
                    raise ValueError("No sufficiently long valid continuous trajectory for this checkpoint") from error
                cutoff = float(data.timestamps[usable[-1][-1]])
                arguments += ["--at-time", str(cutoff)]
                cutoff_note = (f"Final log observations are unsuitable for this checkpoint. Forecast uses the last usable "
                               f"continuous history, ending at source time {cutoff:.6f} s.")
                del data
                result = infer(arguments)
            assert result["model"]["predictor"] == "gru"
            assert result["source"]["sha256"] == row["sha256"]
            assert result["forecast"]["recorded_evidence"] is False
            times = np.asarray(result["forecast"]["timestamps_s"])
            cutoff = result["forecast"]["cutoff_timestamp_s"]
            assert np.all(times > cutoff) and np.all(np.diff(times) > 0)
            assert len(times) == predictor.prediction_steps
            plot = folder / "ml_forecast.png"
            chart(result, plot)
            image = base64.b64encode(plot.read_bytes()).decode("ascii")
            description = (f"<h2>GRU forecast visualization</h2><p>{html.escape(cutoff_note)}</p>"
                           '<p>This is inference with a previously trained development checkpoint; no model was '
                           'retrained on these seven logs. GRU was explicitly requested. The checkpoint automatic '
                           f'choice is <strong>{html.escape(predictor.checkpoint["recommended_predictor"])}</strong> '
                           'based on its original validation data. These forecasts are not an accuracy evaluation '
                           'on this log and have no calibrated prediction interval.</p>'
                           f'<img alt="Observed ENU history and GRU forecast" style="width:100%;height:auto" '
                           f'src="data:image/png;base64,{image}">'
                           '<p><a href="ml_predictions.json">Prediction JSON</a> · '
                           '<a href="forensic_report.html">Forensic report</a></p>')
            page = output_html.read_text()
            page = page.replace('<h2>Forecast estimates</h2>', description + '<h2>Forecast estimates</h2>')
            output_html.write_text(page)
            main_report = folder / "forensic_report.html"
            backup = folder / "forensic_report_without_ml.html"
            if not backup.exists():
                shutil.copy2(main_report, backup)
            text = main_report.read_text()
            if 'id="ml-predictions"' not in text:
                text = text.replace('</body>', '<section id="ml-predictions"><h2>ML trajectory forecast</h2>'
                                    '<p>GRU estimates are provided in a separate appendix, distinct from recorded evidence.</p>'
                                    '<p><a href="ml_report.html">Open ML report and forecast charts</a> · '
                                    '<a href="ml_predictions.json">Prediction JSON</a></p></section></body>')
                main_report.write_text(text)
            info.update(status="passed", report=str(output_html), predictions=str(output_json),
                        cutoff_timestamp_s=cutoff, predicted_steps=len(times), horizon_s=float(times[-1] - cutoff),
                        history_samples=len(result["observed_history"]["timestamps_s"]), cutoff_note=cutoff_note)
            log_path.write_text(json.dumps({"arguments": arguments, "verification": info}, indent=2) + "\n")
            for path in (output_json, output_html, plot, main_report, backup, log_path):
                sidecar(path)
            assert file_hash(acquired) == row["sha256"] == file_hash(row["path"])
            manifest["forecast_requested"] = True
            manifest["artifacts"].update(trajectory_forecast=str(output_json), trajectory_html=str(output_html),
                                         trajectory_plot=str(plot), forensic_report_before_ml=str(backup))
            manifest["ml_supplement"] = {**info, "generated_utc": datetime.now(timezone.utc).isoformat(),
                                          "arguments": arguments, "source_integrity_reverified": True}
            manifest["sha256"] = {str(path.relative_to(folder)): file_hash(path)
                                  for path in sorted(folder.rglob("*"))
                                  if path.is_file() and path not in (manifest_path, Path(str(manifest_path) + ".sha256"))}
            write_json(manifest_path, manifest)
            sidecar(manifest_path)
            for relative, expected in manifest["sha256"].items():
                assert file_hash(folder / relative) == expected, relative
            row.update(ml_status="passed", ml_report=str(output_html), ml_predictions=str(output_json),
                       ml_predictor="gru", artifact_hashes_verified=len(manifest["sha256"]))
        except Exception as error:
            info["error"] = f"{type(error).__name__}: {error}"
            log_path.write_text(traceback.format_exc())
            row.update(ml_status="failed", ml_error=info["error"])
        ml_results.append(info)
        write_json(batch / "ml_batch_results.json", ml_results)
        write_json(batch / "batch_results.json", rows)
        print(f"{info['status'].upper()} {row['slug']}", flush=True)
    # Refresh links without changing the forensic results already recorded.
    from process_pixhawk6c_mini_logs import write_index
    write_index(batch, rows)
    summary = batch / "validation_summary.txt"
    text = summary.read_text().replace(
        "Media and trajectory forecasting were not requested because no media inputs or compatible model checkpoint were supplied.",
        "The initial forensic run used no media or checkpoint. GRU forecast appendices were subsequently added using an existing compatible checkpoint; media analysis remains unrequested.")
    text += (f"\nML supplement: {sum(r['status'] == 'passed' for r in ml_results)}/7 GRU reports generated.\n"
             f"Checkpoint: {snapshot}\nCheckpoint SHA-256: {model_digest}\n"
             "Each forecast uses 20 continuous observations to estimate 10 future positions over 1 second.\n"
             "GRU is explicitly selected; the checkpoint validation-selected predictor is constant acceleration.\n"
             "Original forensic HTML is preserved as forensic_report_without_ml.html in each folder.\n"
             f"Current artifact hashes verified: {sum(r['artifact_hashes_verified'] for r in rows)}\n")
    summary.write_text(text)
    for name in ("index.html", "batch_results.json", "ml_batch_results.json", "validation_summary.txt"):
        sidecar(batch / name)
    assert file_hash(snapshot) == model_digest == file_hash(checkpoint)
    print(f"INDEX: {batch / 'index.html'}", flush=True)
    return 0 if all(row["status"] == "passed" for row in ml_results) else 1


if __name__ == "__main__":
    sys.exit(main())
