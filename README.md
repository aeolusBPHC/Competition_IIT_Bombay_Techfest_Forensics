# Drone Forensics Toolkit

A platform-independent digital forensics and intrusion-analysis framework for unmanned aerial vehicles (UAVs).

The toolkit provides a reproducible workflow for acquiring, preserving, parsing, normalizing, analyzing, and reporting UAV evidence from multiple flight-controller and telemetry ecosystems. It also provides a platform-independent trajectory-processing and machine-learning pipeline for trajectory prediction.

## Project Overview

Modern UAVs generate evidence across multiple layers:

* Flight-controller logs
* Telemetry logs
* GPS/navigation data
* Vehicle state
* Commands and acknowledgements
* Communication events
* Firmware/system information
* Images and video
* Removable storage
* Filesystem and disk-image artifacts

The purpose of this project is to provide a unified forensic workflow that preserves evidence integrity while supporting heterogeneous UAV platforms.

The system is designed around a platform-independent normalized evidence representation. Platform-specific parsers and adapters convert native evidence into this common representation before forensic analysis and machine learning.

---

## Key Objectives

The toolkit currently focuses on:

1. Evidence acquisition and preservation
2. SHA-256 evidence hashing
3. Chain-of-custody tracking
4. Evidence integrity verification
5. Automatic platform detection
6. Platform-specific evidence parsing
7. Normalization of heterogeneous UAV evidence
8. GPS and navigation extraction
9. Flight timeline reconstruction
10. Command/ACK analysis
11. Trajectory reconstruction
12. Multimedia and removable-media forensic analysis
13. Cross-evidence forensic correlation
14. Platform-independent trajectory feature engineering
15. Continuity-aware trajectory windowing
16. Chronological machine-learning evaluation
17. GRU trajectory prediction
18. Constant Velocity and Constant Acceleration baselines

---

# Architecture

```text
                         DRONE FORENSICS TOOLKIT
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │   EVIDENCE ACQUISITION    │
                    │                           │
                    │ Evidence identification   │
                    │ Evidence collection       │
                    │ SHA-256 hashing           │
                    │ Chain of custody          │
                    │ Provenance                │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │   EVIDENCE PROCESSING     │
                    │                           │
                    │ PX4 ULog                  │
                    │ ArduPilot DataFlash/TLog  │
                    │ Betaflight Blackbox       │
                    │ iNav Blackbox             │
                    │ EmuFlight                 │
                    │ MAVLink TLog              │
                    │                           │
                    │ Images / Video            │
                    │ Filesystem artifacts      │
                    │ Disk images               │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │   NORMALIZED EVIDENCE     │
                    │                           │
                    │ timestamps                │
                    │ position                  │
                    │ velocity                  │
                    │ acceleration              │
                    │ commands/events           │
                    │ validity metadata         │
                    │ provenance                │
                    │ source platform           │
                    └─────────────┬─────────────┘
                                  │
                 ┌────────────────┴────────────────┐
                 │                                 │
                 ▼                                 ▼
      ┌─────────────────────┐          ┌─────────────────────┐
      │ FORENSIC ANALYSIS   │          │ MEDIA ANALYSIS      │
      │                     │          │                     │
      │ Timeline            │          │ Images              │
      │ Commands/ACKs       │          │ Video               │
      │ GPS                 │          │ Metadata            │
      │ Flight state        │          │ Removable media     │
      │ Trajectory          │          │ Filesystems         │
      │ Anomalies           │          │ Disk images         │
      └──────────┬──────────┘          └──────────┬──────────┘
                 │                                │
                 └───────────────┬────────────────┘
                                 │
                                 ▼
                    ┌───────────────────────────┐
                    │ CROSS-EVIDENCE CORRELATION│
                    │                           │
                    │ Time correlation          │
                    │ Flight/media correlation  │
                    │ Event correlation         │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │ PLATFORM-INDEPENDENT ML   │
                    │                           │
                    │ Feature engineering       │
                    │ Continuity handling       │
                    │ Temporal windowing        │
                    │ Chronological splitting   │
                    │ Train-only scaling        │
                    │                           │
                    │ GRU                       │
                    │ Constant Velocity         │
                    │ Constant Acceleration     │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │ TRAJECTORY PREDICTION     │
                    │ AND FORENSIC FINDINGS     │
                    └───────────────────────────┘
```

---

# Platform Independence

A major design requirement is that the machine-learning and forensic analysis layers must not depend on a specific flight-controller ecosystem.

Platform-specific evidence is processed through parser/adapter layers.

```text
PX4 ULog ───────────────┐
ArduPilot DataFlash ─── ┤
ArduPilot TLog ─────────┤
Betaflight Blackbox ────┤
iNav Blackbox ──────────┤
EmuFlight ──────────────┤
MAVLink TLog ───────────┤
                        ▼
                Platform Parser
                        │
                        ▼
                NormalizedEvidence
                        │
                        ▼
                NormalizedTrajectory
                        │
                        ▼
              Platform-independent ML
```

This allows the same trajectory-processing and ML pipeline to operate on evidence originating from different UAV platforms.

For platforms where equivalent native fields are unavailable, the system may derive trajectory information from available evidence.

The system does **not** fabricate unavailable evidence. If a defensible mapping cannot be established, the evidence is reported as insufficient for that analysis.

---

# Supported Platforms

| Platform / Format | Evidence Type                 | Processing           |
| ----------------- | ----------------------------- | -------------------- |
| PX4               | ULog                          | Native trajectory    |
| ArduPilot         | DataFlash                     | Native/normalized    |
| ArduPilot         | TLog                          | Normalized           |
| Betaflight        | Blackbox                      | Normalized/derived   |
| iNav              | Blackbox                      | Normalized/derived   |
| EmuFlight         | Blackbox / supported evidence | Non-native / derived |
| MAVLink           | TLog                          | Normalized           |

The architecture is extensible through the parser registry.

---

# Evidence Integrity

Evidence integrity is established before analytical processing.

```text
Evidence acquired
        │
        ▼
SHA-256 calculated
        │
        ├──────────────► Stored in evidence metadata
        │
        └──────────────► Chain-of-custody event
        │
        ▼
Forensic copy created
        │
        ▼
Copy hash verified
        │
        ▼
Evidence analysis
        │
        ▼
Hash re-verification
        │
        ├── MATCH    → evidence unchanged
        │
        └── MISMATCH → integrity violation
```

The SHA-256 hash establishes evidence integrity and provenance. It does not replace the analytical representation of the evidence.

---

# Forensic Workflow

The general workflow is:

```text
Acquire
   ↓
Hash
   ↓
Preserve
   ↓
Verify
   ↓
Identify platform
   ↓
Parse
   ↓
Normalize
   ↓
Analyze
   ↓
Correlate
   ↓
Machine Learning
   ↓
Generate findings
   ↓
Generate report
```

---

# Trajectory Processing

The trajectory subsystem converts platform-specific evidence into a normalized trajectory representation.

A normalized trajectory record may contain:

* Timestamp
* Position
* Velocity
* Acceleration
* Validity flags
* Reset counters
* Source information
* Platform information
* Raw provenance

The ML feature representation currently includes:

```text
x_m
y_m
z_m
vx_m_s
vy_m_s
vz_m_s
speed_m_s
heading_sin
heading_cos
position_valid
```

---

# Continuity-Aware Processing

Trajectory logs may contain:

* Duplicate timestamps
* Non-increasing timestamps
* Logging gaps
* Estimator resets
* Invalid position intervals
* Discontinuities

The preprocessing pipeline therefore does not blindly interpolate across discontinuities.

Trajectory windows are separated when:

1. A trajectory segment changes
2. Timestamps become non-increasing
3. A timestamp gap exceeds the permitted threshold
4. A reset/discontinuity creates a new segment

This prevents artificial motion from being introduced during preprocessing.

---

# Machine Learning Pipeline

The current trajectory prediction pipeline is:

```text
Normalized trajectory
        ↓
Feature engineering
        ↓
Continuity-aware segmentation
        ↓
Temporal resampling
        ↓
Window generation
        ↓
Chronological train/validation/test split
        ↓
Training-only normalization
        ↓
GRU / CV / CA
        ↓
Trajectory prediction
        ↓
ADE / FDE evaluation
```

The current GRU configuration uses:

```text
History length       = 20 steps
Prediction horizon   = 10 steps
Sampling interval    = 0.1 s
History duration     = 2.0 s
Prediction duration  = 1.0 s
```

The GRU is currently implemented as a baseline recurrent model.

Constant Velocity (CV) and Constant Acceleration (CA) models are also used as physics-based baselines.

---

# Synthetic Dataset

A synthetic trajectory benchmark is included for controlled evaluation.

Current configuration:

```text
Trajectories       : 100
Train              : 70
Validation         : 15
Test               : 15
Duration           : 60 s
Sampling frequency : 10 Hz
Interval           : 0.1 s
Noise              : 0.02 m
Seed               : 20260927
```

Scenarios include:

* Accelerate/decelerate
* 90-degree turn
* Smooth turn
* Circle
* Climb and cruise
* Figure eight
* Stop-turn-stop
* Mixed 3D motion

The synthetic benchmark is used to evaluate the trajectory models under controlled conditions.

---

# Case Study: CASE-001

The current PX4 forensic case contains:

```text
Platform       : PX4 SITL
Evidence       : PX4 ULog
Datasets       : 85
Log duration   : approximately 43 min
GPS samples    : 70,755
Trajectory     : native vehicle_local_position
```

The normalized trajectory contains approximately:

```text
252,564 usable trajectory samples
```

The trajectory contains two continuity segments due to estimator/reset handling.

The trajectory pipeline verifies that the previously observed extreme derived velocity artifact is not present in the cleaned native trajectory.

Current maximum usable speed:

```text
6.022651 m/s
```

Samples above:

```text
10 m/s  : 0
100 m/s : 0
```

---

# Forensic Analysis

The toolkit currently supports:

## GPS extraction

Extracts GPS observations from flight-controller evidence.

Output examples:

```text
gps_data.csv
gps_data.json
```

## Timeline reconstruction

Reconstructs chronological forensic events including:

* Vehicle commands
* Command acknowledgements
* GCS connection state changes

## Command analysis

Analyzes:

* Vehicle commands
* Command IDs
* Acknowledgements
* Command timing

## Flight-state analysis

Flight-controller state information can be used to analyze:

* Arming state
* Navigation state
* GCS connection state
* Landing-related state

---

# Media Forensics

The toolkit also includes multimedia and removable-media forensic processing.

Supported evidence categories include:

```text
Images
Video
Media metadata
Removable media
Filesystems
Disk images
```

External forensic tooling currently installed includes:

```text
Sleuth Kit
dosfstools
mtools
```

Media evidence is intentionally kept as a separate forensic branch.

Media metadata can later be correlated with telemetry and flight timelines, but media is not automatically treated as GRU trajectory input.

---

# Testing

The project uses `pytest`.

Current verified results include:

```text
Media tests:
38 passed, 13 skipped

Full repository:
226 passed, 13 skipped
```

Trajectory/windowing tests:

```text
8 passed
```

Trajectory + GRU integration tests:

```text
12 passed
```

The complete test suite should be run before publishing a new version.

---

# Installation

## 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd drone_forensics
```

## 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Upgrade pip

```bash
python -m pip install --upgrade pip
```

## 4. Install Python dependencies

```bash
pip install -r requirements.txt
```

If the requirements file has not yet been finalized:

```bash
pip install pyulog pandas numpy matplotlib pytest torch
```

---

# System Dependencies

For media and filesystem analysis:

```bash
sudo apt update
sudo apt install sleuthkit dosfstools mtools
```

Verify:

```bash
which fls
which fsstat
which mmls
which icat
which mkfs.fat
which mcopy
```

---

# Running the Test Suite

Run the media tests:

```bash
pytest -q tests/media
```

Fetch the verified media test samples:

```bash
bash tools/fetch_media_samples.sh
```

Then:

```bash
MEDIA_SAMPLES_DIR=tests/fixtures/media_samples pytest -q tests/media
```

Run the complete test suite:

```bash
pytest -q
```

---

# Evidence Acquisition

A typical evidence acquisition command is:

```bash
python -m acquisition.acquire \
    --input /path/to/evidence.ulg \
    --case CASE-001
```

The acquisition stage records:

* Evidence metadata
* Original SHA-256
* Forensic-copy SHA-256
* Integrity verification
* Chain-of-custody events
* Evidence provenance

---

# Inspecting Evidence

List case evidence:

```bash
find repository/cases -type f | sort
```

Inspect metadata:

```bash
cat repository/cases/CASE-001/<EVIDENCE_ID>/metadata.json
```

Calculate a SHA-256 hash:

```bash
sha256sum /path/to/evidence.ulg
```

---

# PX4 ULog Analysis

For a PX4 ULog:

```bash
python -m cli.main \
    --input /path/to/evidence.ulg \
    --case-id CASE-001
```

The parser identifies PX4 ULog evidence and converts the available records into the normalized evidence model.

The normalized representation can then be consumed by downstream forensic and ML components.

---

# Trajectory Dataset Inspection

Build a trajectory dataset from evidence using the trajectory feature pipeline.

The trajectory dataset contains:

```text
timestamps
positions
velocities
features
feature_names
segment_ids
accelerations
trajectory_source
```

For native PX4 trajectory evidence, the source is recorded as:

```text
native_or_normalized
```

For defensibly derived non-native trajectory evidence:

```text
derived
```

---

# GRU Training

The GRU trainer is executed as a Python module:

```bash
python -m ml.trajectory_gru_train --help
```

Available options include:

```text
--input INPUT
--synthetic-root SYNTHETIC_ROOT
--case-id CASE_ID
--output OUTPUT
--model-output MODEL_OUTPUT
--epochs EPOCHS
--batch-size BATCH_SIZE
--hidden-size HIDDEN_SIZE
--layers LAYERS
--learning-rate LEARNING_RATE
--patience PATIENCE
--target-mode {absolute,relative}
```

Example real-evidence training command:

```bash
python -m ml.trajectory_gru_train \
    --input repository/cases/CASE-001/EVD-20260919-175126/evidence/17_02_27.ulg \
    --case-id CASE-001 \
    --output reports/CASE-001/gru_results.json \
    --model-output reports/CASE-001/gru_model.pt
```

Example with a smaller training run:

```bash
python -m ml.trajectory_gru_train \
    --input repository/cases/CASE-001/EVD-20260919-175126/evidence/17_02_27.ulg \
    --case-id CASE-001 \
    --output reports/CASE-001/gru_results.json \
    --model-output reports/CASE-001/gru_model.pt \
    --epochs 5
```

The trainer:

1. Parses the evidence
2. Builds the normalized trajectory
3. Performs chronological splitting
4. Generates continuity-aware windows
5. Fits feature normalization on training data only
6. Fits target normalization on training data only
7. Trains the GRU
8. Evaluates validation/test data
9. Saves the model
10. Writes evaluation results

---

# Important ML Evaluation Rule

The project does not randomly split temporal windows.

Instead:

```text
EARLIER FLIGHT DATA
        │
        ├── Training
        │
        ├── Validation
        │
        └── Test
        │
        ▼
LATER FLIGHT DATA
```

This reduces temporal leakage.

Normalization is also fitted exclusively on training data:

```text
Training data
     ↓
fit scaler
     ↓
Validation/Test
     ↓
transform only
```

---

# Synthetic Training

Synthetic trajectory data can be used to test the ML pipeline independently of a specific UAV platform.

Example:

```bash
python -m ml.trajectory_gru_train \
    --synthetic-root repository/synthetic_datasets/trajectory_v1 \
    --case-id SYNTHETIC-V1 \
    --output reports/synthetic/gru_results.json \
    --model-output reports/synthetic/gru_model.pt
```

---

# Reproducibility

The project records:

* Evidence hashes
* Case identifiers
* Evidence identifiers
* Parser/platform information
* Source trajectory
* Dataset configuration
* ML parameters
* Random seeds where applicable
* Test results
* Generated forensic outputs

This allows experiments to be reproduced without coupling the analytical layer to one UAV platform.

---

---

# Development Status

## Implemented

* Evidence acquisition
* SHA-256 hashing
* Forensic-copy verification
* Chain-of-custody tracking
* Evidence metadata
* Platform parser registry
* PX4 ULog parsing
* ArduPilot support
* Betaflight support
* iNav support
* EmuFlight support
* MAVLink TLog support
* Normalized evidence representation
* Native trajectory extraction
* Derived trajectory support
* GPS extraction
* Timeline reconstruction
* Command/ACK analysis
* Media forensic processing
* Filesystem/disk-image tooling
* Continuity-aware trajectory preprocessing
* Temporal trajectory windowing
* Chronological ML splitting
* Training-only normalization
* GRU trajectory prediction
* Constant Velocity baseline
* Constant Acceleration baseline
* Automated test suite

## In Progress / Future Work

* Multi-flight leave-one-flight-out evaluation
* Larger cross-platform trajectory benchmark
* Uncertainty-aware trajectory prediction
* More advanced sequence models
* Additional anomaly/detection models
* Expanded cross-evidence correlation
* More platform-specific forensic mappings
* Additional real-world datasets

---

# Validation Summary

The current repository has been validated using automated tests.

Latest full-suite result:

```text
226 passed, 13 skipped
```

Media-specific validation:

```text
38 passed, 13 skipped
```

Trajectory/windowing validation:

```text
8 passed
```

Trajectory + GRU integration validation:

```text
12 passed
```

These results indicate that the currently implemented acquisition, parser, media, trajectory-processing, and ML integration components are passing their automated validation suite.

---

# Project Philosophy

The project follows four principles:

### 1. Evidence first

Evidence must be preserved and integrity-verified before analysis.

### 2. Platform independence

Forensic analysis and machine learning should operate on normalized representations rather than platform-specific fields.

### 3. No fabricated evidence

When the available evidence cannot support a mapping or conclusion, the system reports insufficient evidence instead of generating unsupported values.

### 4. Reproducibility

Every important processing stage should be executable through documented commands and validated through automated tests.

---

# License

MIT License.

---



