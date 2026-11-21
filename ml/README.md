# Trajectory prediction

This package forecasts short-horizon 3D positions from parsed drone logs or
synthetic observations. It compares a GRU with constant-velocity (CV) and
constant-acceleration (CA) models. Forecasts are estimates and are stored
separately from recorded evidence.

Run commands from the repository root. The examples use the existing `.venv`.
`ml/requirements.txt` records the direct dependency versions used for validation.
Each run also records its actual Python/dependency versions, code hashes, source
hashes, arguments, seed, feature order, coordinate convention, and data splits.

## Data and coordinates

All normalized trajectories use **ENU**: x east, y north, z up, with metres,
metres/second, and metres/second². The PX4 adapter converts native NED coordinates
and retains the original values in `TrajectoryRecord.raw`. This follows the
[PX4 local-position definition](https://docs.px4.io/main/en/msg_docs/VehicleLocalPosition).
The GPS fallback uses a local tangent-plane approximation based on the first
valid geodetic observation. Origins are recorded with source provenance; ENU
axes do not imply that different flights share an origin.

The ten ordered inputs are x/y/z, vx/vy/vz, speed, heading sine, heading cosine,
and position validity. Heading means **course counterclockwise from east**,
derived from velocity for real logs. GPS antenna/body yaw is not substituted for
course. Synthetic data can contain a separately noisy course measurement.

`TrajectoryDataset` is shared by real and synthetic loaders. Slicing preserves
segment IDs, accelerations, clean target positions, and provenance. Invalid
positions, reset boundaries, duplicate/reversed timestamps, and large gaps split
trajectories before window creation. XY and vertical position resets are treated
conservatively as segment boundaries. Derived velocities use backward differences
within segments; the first sample has no defensible derivative and uses zero.

Input resampling holds the most recent available observation, so no feature uses
a record from after the forecast cutoff. Target positions are interpolated
separately. By default, 20 history samples at 0.1 s spacing span 1.9 s; the next
10 predicted positions extend from +0.1 to +1.0 s.

## Generate synthetic observations with clean targets

```bash
.venv/bin/python -m ml.synthetic_trajectory \
  --output-dir repository/synthetic_datasets/trajectory_v2 \
  --train-count 70 --validation-count 16 --test-count 16 \
  --duration 60 --seed 20260927
```

The eight scenarios are distributed across each split. Each NPZ stores noisy
`position` and `velocity` observations, measured course, validity, reset segments,
and separate clean `ground_truth_position` and `ground_truth_velocity` arrays.
Ground truth is used only for targets, never as input features. Metadata stores
each trajectory seed, file hash, ENU frame, and noise configuration.

The configurable noise includes position and velocity errors, heading error,
random-walk position drift, bounded timing jitter, isolated dropouts, longer
outages, and estimator position corrections. Defaults are illustrative, not
calibrated to a real sensor. For example:

```bash
.venv/bin/python -m ml.synthetic_trajectory \
  --output-dir /tmp/trajectory_sensor_experiment \
  --position-noise-std 0.3 --velocity-noise-std 0.2 \
  --timing-jitter-std 0.02 --dropout-probability 0.02 \
  --outage-probability 0.5 --reset-probability 0.5
```

Generation refuses to overwrite an existing trajectory dataset. Original V1 NPZ
files remain loadable; because they lack clean targets, their labels are marked
`noisy_observation`. Real-log labels are marked `estimator_observation`. Neither
is presented as independently measured flight ground truth.

## Train and compare models

```bash
.venv/bin/python -m ml.trajectory_gru_train \
  --synthetic-root repository/synthetic_datasets/trajectory_v2 \
  --case-id SYNTHETIC-V2 \
  --output reports/SYNTHETIC-V2/benchmark.json \
  --model-output reports/SYNTHETIC-V2/gru.pt \
  --input-frame heading --target-mode residual_velocity \
  --seeds 42 43 44
```

Default inputs are centered on the final observed position. `--input-frame
heading` also rotates positions, velocities, and course into the most recent
reliable observed direction of travel; predictions are rotated back to ENU.
`--input-frame global` retains absolute positions for controlled comparisons.

Targets can be `relative`, `residual_velocity` (the default), or
`residual_acceleration`. Residual models learn a correction to the relevant
physics forecast. `absolute` targets require `--input-frame global` because a
centered history does not contain the absolute origin. Both scalers are fitted
only on training windows. Early stopping uses validation loss.

Additional controls include `--history-steps`, `--prediction-steps`, `--interval`,
`--epochs`, `--patience`, `--hidden-size`, `--layers`, `--learning-rate`,
`--batch-size`, `--threads`, and `--device cpu|cuda|auto`. A single reproducible
run uses `--seed 42`; repeated runs use `--seeds 42 43 44`. Extra checkpoints use
names such as `gru.seed-43.pt`; the first seed keeps the requested filename.
The first seed is not chosen using test performance.

For every checkpoint, the default inference predictor is whichever of GRU, CV,
or CA has the lowest **validation flight-macro ADE**. Test results do not choose
the predictor. An improved representation does not by itself establish that a
GRU outperforms physics; the saved comparisons must demonstrate that.

## Hold out complete flights, missions, or platforms

Use a JSON manifest with nonempty `train`, `validation`, and `test` lists:

```json
{
  "train": [{"path": "flights/a.ulg", "flight_id": "a", "mission": "survey-a", "platform": "PX4"}],
  "validation": [{"path": "flights/b.ulg", "flight_id": "b", "mission": "survey-b", "platform": "PX4"}],
  "test": [{"path": "flights/c.ulg", "flight_id": "c", "mission": "survey-c", "platform": "PX4"}]
}
```

Paths are relative to the manifest. Flight IDs, resolved paths, and file content
hashes must be unique; copied or renamed evidence cannot occur in multiple
splits. Assign the same canonical mission identifier to every log from one
mission. Supplied platform labels must match the parsed source.

```bash
.venv/bin/python -m ml.trajectory_gru_train \
  --manifest ml/examples/flights.example.json --holdout-group mission \
  --case-id FLIGHT-HOLDOUT --output reports/FLIGHT-HOLDOUT/benchmark.json \
  --model-output reports/FLIGHT-HOLDOUT/gru.pt --seeds 42 43 44
```

`--holdout-group mission` rejects missions shared across splits.
`--holdout-group platform` requires distinct platforms across all three splits,
allowing explicit evaluation on unseen platforms. The included example contains
only PX4 flights and is a wiring example for mission holdout. Its CASE-004 test
flight is short and mostly stationary; it is not a representative generalization
benchmark. Add more independent moving flights and platforms for that purpose.

`--input path/to/flight.ulg` remains available for chronological 70/15/15
exploration within one flight. It is explicitly marked as a single-flight
experiment, and no confidence interval across independent flights is reported.

Results include window-weighted ADE/FDE, per-flight metrics, equal-flight macro
metrics, motion/scenario/platform/label-kind breakdowns, horizon errors, and
paired GRU-versus-physics differences. Across seeds, reports give the mean and
sample standard deviation of flight-macro metrics. 95% bootstrap intervals
resample independent test-flight means averaged across seeds, not overlapping
windows. They require at least two held-out flights and describe aggregate
performance on that sample of flights, not the uncertainty of a forecast path.

## Load checkpoints and produce a forecast appendix

```bash
.venv/bin/python -m cli.main trajectory-predict \
  --input repository/cases/CASE-003/raw/px4_sitl_qgc_mission.ulg \
  --checkpoint reports/FLIGHT-HOLDOUT/gru.pt \
  --output reports/FLIGHT-HOLDOUT/forecast.json \
  --report reports/FLIGHT-HOLDOUT/forecast.html \
  --case-id CASE-003
```

The same arguments work with `python -m ml.trajectory_inference`. `--at-time`
limits history to a source-clock timestamp. Only recent continuous observations
are required; inference does not require future labels. The default
`--predictor selected` uses validation selection; `gru`, `constant_velocity`,
and `constant_acceleration` allow explicit comparisons.

JSON and HTML separate causally resampled observations from forecast estimates.
They record source and checkpoint hashes, source origin, coordinate axes,
sampling, training provenance, selected predictor, and the source-clock cutoff.
No calibrated path prediction interval is currently available. Output paths
cannot overwrite the input evidence or checkpoint.

**Checkpoint migration:** checkpoints written by the old pipeline have no
reliable ENU/preprocessing contract and must be retrained. The loader rejects
them with a migration message. Historical saved benchmark JSON and checkpoint
files are retained; their scores are not directly comparable to the new causal,
ENU, clean-target pipeline.

## Validation

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/ml tests/test_trajectory_gru_integration.py \
  tests/test_trajectory_windowing.py tests/test_case001_trajectory_regression.py
```

Coverage includes V1/V2 synthetic loading and windowing, NED-to-ENU conversion
with preserved raw values, causal input resampling, invalid/reset boundaries,
translation/rotation invariance, training-only normalization, manifest leakage
checks, repeated-seed training, checkpoint reloads, forecast JSON/HTML, and the
forensic CLI. Small training runs verify the workflow; longer independent-flight
experiments are still required to make a performance claim.
