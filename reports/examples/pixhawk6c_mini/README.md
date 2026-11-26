# Pixhawk 6C Mini example reports

Seven public logs processed with the toolkit, with a separate explicit GRU forecast for each case.

| Reported case | Forensic report | ML report | PNG preview |
| --- | --- | --- | --- |
| Attitude / roll failsafe | [Forensic HTML](attitude_failsafe/forensic_report.html) | [GRU HTML](attitude_failsafe/ml_report.html) | [Forecast chart](attitude_failsafe/ml_forecast.png) |
| Offboard altitude loss; optical flow, no GPS | [Forensic HTML](offboard_no_gps/forensic_report.html) | [GRU HTML](offboard_no_gps/ml_report.html) | [Forecast chart](offboard_no_gps/ml_forecast.png) |
| Motor oscillation and overheating | [Forensic HTML](motor_oscillation/forensic_report.html) | [GRU HTML](motor_oscillation/ml_report.html) | [Forecast chart](motor_oscillation/ml_forecast.png) |
| Unexpected movement in Land mode | [Forensic HTML](land_mode/forensic_report.html) | [GRU HTML](land_mode/ml_report.html) | [Forecast chart](land_mode/ml_forecast.png) |
| Battery status investigation: original power module | [Forensic HTML](battery_original/forensic_report.html) | [GRU HTML](battery_original/ml_report.html) | [Forecast chart](battery_original/ml_forecast.png) |
| Battery status investigation: comparison power module | [Forensic HTML](battery_comparison/forensic_report.html) | [GRU HTML](battery_comparison/ml_report.html) | [Forecast chart](battery_comparison/ml_forecast.png) |
| EKF altitude estimation discrepancy | [Forensic HTML](ekf_altitude/forensic_report.html) | [GRU HTML](ekf_altitude/ml_report.html) | [Forecast chart](ekf_altitude/ml_forecast.png) |

GitHub previews PNG files and this Markdown table. To view the HTML reports, download this complete directory and open `index.html` in a browser. All HTML images are embedded.

These are publication copies with local path strings normalized. Numerical observations, forecasts, and input/model hashes are unchanged. Original artifact hashes are recorded in `publication_manifest.json`; fresh `.sha256` sidecars cover the published copies.

GRU was explicitly requested. The checkpoint default selects constant acceleration using its original validation data. Each appendix forecasts ten future ENU positions over one second from twenty history observations; it does not report measured accuracy on these logs.

The source logs and model weights are not included. See `sources.json` for public download URLs and SHA-256 identifiers. Viewing these examples needs neither the logs nor the checkpoint; reproducing them needs both a supported log and a compatible checkpoint.

[Validation results](../../validation_summary.json)
