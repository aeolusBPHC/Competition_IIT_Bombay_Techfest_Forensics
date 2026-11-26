# GitHub changes: November 20–25, 2026

Reviewed HEAD: `2e691e5e9fa50db360fb408f7772630cd4d327dd`.
The recent burst contains **46 commits**, including one merge.
The preceding commit is `f35a9ac`, September 27 UTC / September 28 IST, about two
months earlier. Dates below are UTC. The November 25 19:13 merge occurred
November 26 at 00:43 IST.

## Changes by area

- **November 20 — parsers and reporting:** Expanded DataFlash, MAVLink and
  Blackbox extraction; added shared coverage, inventories and raw observations;
  added navigation/trajectory/battery/telemetry/failsafe fields, GPS2,
  EKF/odometry, cell voltages, extended parameters and decoder diagnostics.
  Refactored adapters and added regression tests. Updated normalized reports
  and CLI counts; added the trajectory prediction CLI.
- **November 21 — ML:** Refactored dataset/windowing/quality/training; added noisy
  synthetic observations with clean targets, causal resampling, train-only
  standardization, residual targets, frame transforms, flight manifests/group
  holdouts, repeated seeds, validation-selected GRU/CV/CA inference, provenance,
  forecast JSON/HTML, package docs, dependencies, examples and tests. Legacy
  checkpoints are not automatically compatible with the current contract.
- **November 25 — media:** Deepak Ramalingam's
  [PR #1](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/pull/1)
  adds sampled video frame timelines/JPEG previews, GoPro GPMF and ExifTool-based
  DJI telemetry, clock/position anomaly review, filesystem timestamps, and HTML
  gallery/timeline rendering with portable hash-verified media copies.
  The feature changes **19 files: +2,532 / −67 lines**. It adds source code,
  documentation and tests, rather than a batch of actual photos/videos.

## Review findings and local implementation

The pushed generic MAVLink module defines `ArduPilotTLogParser` instead of
`MAVLinkTLogParser`. This prevents the registry from importing and blocks all
registered formats. The local review restores generic detection while retaining
extended extraction. The pushed `process` command only acquires evidence and
leaves analysis/reporting as placeholders. The local implementation connects
those stages, optional media/forecasting, output manifests and unique acquisition
IDs. Recovered disk-image media resolves to retained derivatives for gallery use.
These local changes are separate from the GitHub history and have not been pushed.

## Every recent commit (newest first)

| UTC date | Commit | Change |
| --- | --- | --- |
| 2026-11-25 | [2e691e5](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/2e691e5e9fa50db360fb408f7772630cd4d327dd) | Merge pull request #1 from deepakramalingamk/feature/video-telemetry-forensics |
| 2026-11-25 | [bc85573](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/bc85573c98d7ef80638791d0152e6906e0f33f36) | Add media forensics features |
| 2026-11-21 | [9609158](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/96091583ec494e781b6e5e8b30ad2528c2ca666f) | Implement tests for trajectory workflow |
| 2026-11-21 | [dde34ba](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/dde34bab97b485579d87b886b1af1abc71bec783) | Implement tests for synthetic trajectory and parsing |
| 2026-11-21 | [7d90547](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/7d9054735ba5b575bb95619eb3c011701061b537) | Add trajectory report generation function |
| 2026-11-21 | [2b96767](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/2b96767e1776373c747f9c85710b43dfb8bfcc2b) | Add example flight data in flights.example.json |
| 2026-11-21 | [5d30365](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/5d30365fa645f2b474132653846c754283756cd0) | Add requirements for ML validation dependencies |
| 2026-11-21 | [1346274](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/13462741796e6c76ba5ac560954ec228091bb5ad) | Add README for trajectory prediction package |
| 2026-11-21 | [c59763a](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/c59763ae620f23d6ee7e7e7a97ffd15a0018354b) | Add trajectory provenance module with various functions |
| 2026-11-21 | [9118ba5](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/9118ba54bcf594398d34d636877e7a46182162c1) | Add trajectory inference functionality |
| 2026-11-21 | [193ca8d](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/193ca8d41a110ab2d0b6d4c91474e9b3e3f61dfd) | Add trajectory evaluation metrics and summary functions |
| 2026-11-21 | [f8aa542](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/f8aa542ffe090a468c015fce73ee6adbedd99a71) | Add trajectory preprocessing module with standardization |
| 2026-11-21 | [7014660](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/7014660d39bf3a7d2d982fa16ceea04e44abe8e4) | Add trajectory_data.py for loading flight data |
| 2026-11-21 | [f836784](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/f83678463e599b483f4f609e46a39ca165631756) | Refactor trajectory window creation logic |
| 2026-11-21 | [bba0129](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/bba01296ded3a43bc17db2fa4c1ba019edff1018) | Refactor make_subdataset function |
| 2026-11-21 | [a31302a](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/a31302a33d3a2314a1eaca8a9261bfcde5eef5f9) | Reworked training, evaluation, selection, and checkpoints |
| 2026-11-21 | [c0d4d52](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/c0d4d52c69d62b20afc9aa21f92d4dd063dece64) | Refactor trajectory dataset functions and improve error handling |
| 2026-11-21 | [fd66eda](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/fd66edae7caa45bf52490e0ae9440e13ffad6117) | Enhance trajectory features and dataset structure |
| 2026-11-21 | [bbd01c6](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/bbd01c65e0c5d0743dfcfca7d763fbc834423e3a) | Refactor synthetic trajectory dataset loading functions |
| 2026-11-21 | [4b0b55b](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/4b0b55b5c8834854948018325c1f7c67e596ba29) | Enhance synthetic trajectory generation with noise |
| 2026-11-20 | [5053602](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/5053602216a456847fce0b45c64e47afb0446a67) | Implement regression tests for dataflash and tlog parsers |
| 2026-11-20 | [1d18de3](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/1d18de36b3f78846b271455c3d3fe517ee48f613) | Add extended_extractors for MAVLink evidence processing |
| 2026-11-20 | [e296ae7](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/e296ae7e1316f277cd2a469a64271fbc4ce53ba5) | Add DataFlashEvidenceMixin for data extraction |
| 2026-11-20 | [54ce0a2](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/54ce0a252185501d29874baa36ef62181805de2b) | Add BlackboxEvidenceMixin for blackbox data processing |
| 2026-11-20 | [9224543](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/922454314610381bda021452a0890e193eeaf5a4) | Add extraction functions for evidence coverage |
| 2026-11-20 | [bb1dd02](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/bb1dd020b87234fa3742e4781a2bbe625ad39468) | Enhance README with parser coverage and usage details |
| 2026-11-20 | [4a247c9](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/4a247c9b2484bb343a4df7ef9c1fdbadfb5f5b19) | Create README.md |
| 2026-11-20 | [3a59393](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/3a59393cc8dea931f3ad2f64db4fdeb8ed0dbe4a) | Refactor test assertions for MAVLink extractors |
| 2026-11-20 | [94eeaa7](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/94eeaa7b85962e334bec21bc85afd2d953b55682) | Enhance parameter extraction assertions in tests |
| 2026-11-20 | [269318a](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/269318a8286b225d1518922a5df42c6a3a45822b) | Refactor test for unavailable categories and GPS extraction |
| 2026-11-20 | [d7890cd](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/d7890cd9ac39613766015202776c28f2f598b229) | Add record counts for navigation, trajectory, and battery |
| 2026-11-20 | [939d40c](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/939d40cef6562b5470d903c12dff03e2ccf3080c) | Enhance parameter extraction tests in betaflight blackbox |
| 2026-11-20 | [c23970c](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/c23970ce4a84220bfcbbb7a41d9ffad54d83ca1f) | Refactor report generation to use dynamic categories |
| 2026-11-20 | [21f04c9](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/21f04c9f3440a0677de2ab36106d68c99fdaa8f5) | Refactor trajectory record fields and add data extraction |
| 2026-11-20 | [f755d5e](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/f755d5e59d1739a9f8c161e58248e718829a8517) | Refactor EmuFlightBlackboxParser methods and structure |
| 2026-11-20 | [9ed6f35](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/9ed6f35bccd52994dd417f5eb25174666886fa9b) | Add decode_error_samples to track decode errors |
| 2026-11-20 | [834ca49](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/834ca491bcbd613b60d80547001d306550a05e09) | Refactor INAVBlackboxParser to use mixins |
| 2026-11-20 | [1ae163e](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/1ae163e3169aa95ab54b9dc018a51c5c804e8fb0) | Refactor BetaflightBlackboxParser methods |
| 2026-11-20 | [3db21bf](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/3db21bf8e0365449534c4032ab05812cfabe3387) | Refactor telemetry and failsafe record handling |
| 2026-11-20 | [b9bf592](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/b9bf59262168dceadec73a44ee2de1eabc48e43b) | Added expansions |
| 2026-11-20 | [8c62357](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/8c62357637eb39a6243d7c27a55b8a1a4d0541a1) | Refactor TLOG parser to use mavlink_decoder |
| 2026-11-20 | [aa465e5](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/aa465e5aae3cb2a0b1828ab60c36c40cbdafc1e0) | Added extended extraction |
| 2026-11-20 | [bdb7589](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/bdb7589513d6bb0a62f23fc90feaf73e521a488f) | Add new fields to telemetry and failsafe records |
| 2026-11-20 | [e3a4bf1](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/e3a4bf1adc96249b182c96fcdc4c9ddd968f4881) | Implement extract_additional_data method |
| 2026-11-20 | [442e883](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/442e88347dc5e7ea3d1d3556bfcafa6615208065) | Enhance CLI with trajectory prediction feature |
| 2026-11-20 | [d8a6122](https://github.com/aeolusBPHC/Competition_IIT_Bombay_Techfest_Forensics/commit/d8a6122ab10c7d7769c21b1b2870b3568141069d) | Add trajectory and failsafe_active counts to analysis |

## Complete file inventory

Compared with the preceding September commit, GitHub changed **62 files**:
**6,259 additions and 3,461 deletions**. The following inventory comes from
`git diff --name-status f35a9ac..2e691e5`.

```text
M	MEDIA_EXTRACTOR.md
M	README.md
M	analysis/normalized_analysis.py
M	cli/main.py
A	media/anomalies.py
A	media/embedded_telemetry.py
M	media/extractor.py
A	media/filesystem_timeline.py
A	media/frame_timeline.py
A	media/gpmf.py
A	ml/README.md
A	ml/examples/flights.example.json
A	ml/requirements.txt
M	ml/synthetic_trajectory.py
M	ml/synthetic_trajectory_dataset.py
M	ml/trajectory_benchmark.py
A	ml/trajectory_data.py
M	ml/trajectory_dataset.py
A	ml/trajectory_evaluation.py
M	ml/trajectory_features.py
M	ml/trajectory_gru_train.py
A	ml/trajectory_inference.py
A	ml/trajectory_preprocessing.py
A	ml/trajectory_provenance.py
M	ml/trajectory_quality.py
A	platform_parsers/README.md
A	platform_parsers/ardupilot/dataflash_extensions.py
M	platform_parsers/ardupilot/dataflash_parser.py
M	platform_parsers/ardupilot/tlog_parser.py
M	platform_parsers/betaflight/blackbox_parser.py
M	platform_parsers/common/base_parser.py
A	platform_parsers/common/blackbox_evidence.py
M	platform_parsers/common/evidence_model.py
A	platform_parsers/common/extraction.py
M	platform_parsers/emuflight/blackbox_decoder.py
M	platform_parsers/emuflight/blackbox_parser.py
M	platform_parsers/inav/blackbox_parser.py
A	platform_parsers/mavlink/extended_extractors.py
M	platform_parsers/mavlink/normalized_extractors.py
M	platform_parsers/mavlink/tlog_parser.py
M	platform_parsers/px4/ulog_parser.py
A	reporting/evidence_gallery.py
A	reporting/filesystem_timeline_view.py
M	reporting/normalized_report.py
M	reporting/normalized_report_generator.py
A	reporting/trajectory_report.py
A	tests/media/test_anomalies.py
A	tests/media/test_embedded_telemetry.py
A	tests/media/test_filesystem_timeline.py
A	tests/media/test_frame_timeline.py
A	tests/media/test_gpmf.py
M	tests/media/test_media_extraction.py
A	tests/ml/test_trajectory_contract.py
A	tests/ml/test_trajectory_workflow.py
A	tests/reporting/test_evidence_gallery.py
A	tests/reporting/test_filesystem_timeline_view.py
M	tests/test_betaflight_blackbox.py
M	tests/test_cli_normalized_analysis.py
M	tests/test_emuflight_blackbox.py
M	tests/test_inav_blackbox.py
M	tests/test_mavlink_normalized_extractors.py
A	tests/test_parser_extended_evidence.py
```

## Local validation

- Full suite after restoring the generic parser and implementing the runner:
  **286 passed, 15 skipped** (226.78 seconds).
- Runner/gallery regression checks after the final additional path-resolution test:
  **5 passed**.
- Actual `python -m cli.main process --input ...` smoke run completed on the
  synthetic DataFlash fixture: JSON, HTML, 11 PNG plots, and 14 manifest hashes
  verified. A local example is at `/tmp/drone-forensics-example-report/`.
- Tests used the existing Python 3.12 virtual environment, `MPLBACKEND=Agg`,
  and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` to avoid unrelated ROS pytest plugins.
- Seven bundled Git LFS files were temporarily populated using SHA-256-matching
  copies already on disk. Their pointer files were restored after validation.
  No source evidence in the original checkout was modified.
- Optional external-sample/tool tests remain skipped in this environment.

Nothing was committed, pushed, or changed on GitHub. Changes are prepared only
in the separate local review checkout.
