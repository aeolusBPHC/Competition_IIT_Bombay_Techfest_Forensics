# Parser coverage and normalized evidence

The seven registered adapters share `BaseForensicParser.parse()` and one
`NormalizedEvidence` contract. Every parse includes GPS, navigation, trajectory,
battery, telemetry, failsafe/health, commands, command acknowledgements, states,
parameters, events, and additional source observations. All native metric
trajectories use ENU: x east, y north, z up.

Matching PX4 means extracting the available evidence into the same categories
and retaining source data, rather than forcing other logs to have PX4's record
count. Counts depend on flight duration, sensor availability, logging settings,
message rate, and firmware. A healthy status sample is still a health record;
the number of failsafe records is not the number of active failures.

## Implemented mappings

| Adapter | Main normalized evidence and additions |
| --- | --- |
| PX4 ULog | Native GPS/navigation/local trajectory, batteries, telemetry, failsafe flags, commands/ACKs, states, parameters, events; topic/field inventory and platform metadata |
| ArduPilot DataFlash | GPS/GPS2, POS, XKF1/NKF1 native trajectories with XKF4/NKF4 solution validity, BAT battery health/remaining charge, BCL cell voltages, RAD radio statistics, explicit ERR failsafe activation/recovery, MODE/ARM, MAVC, PARM, EV/ERR/MSG |
| ArduPilot TLOG | Shared MAVLink GPS and GPS2_RAW, global navigation, local-position/odometry trajectories, battery, radio/communication statistics, estimator/fence/sensor health, commands/ACKs, states, standard and extended parameters, STATUSTEXT |
| Generic MAVLink TLOG | The same MAVLink mappings, without assuming an ArduPilot platform identity |
| Betaflight Blackbox | I/P/G/H/S/E decoding, GPS/navigation, calibrated battery readings, receiver RSSI, slow-frame states/failsafe phases and RC loss, configuration headers, events; raw IMU/PID/motor/RC fields retained |
| INAV Blackbox | Full common Blackbox decoding plus native `navPos`/`navVel` ENU trajectories, `navFlags` validity, supported modern battery readings, receiver RSSI, states/failsafes, configuration headers, events |
| EmuFlight Blackbox | Existing full decoder, GPS/navigation, configured battery conversions, receiver RSSI when recorded, states/failsafe phases, configuration headers/events, full raw-frame preservation |

Availability remains specific to the source:

- DataFlash MAVC records are commands, not proof of command acknowledgement.
- Blackbox does not carry a MAVLink-style command/ACK protocol. Betaflight and
  EmuFlight body IMU data is not relabeled as a native local-position trajectory.
- DataFlash native trajectory validity requires a recorded corresponding EKF
  solution status. Uncertified numeric samples are retained with validity false.
- INAV navigation positions and velocities are north/east/up in centimetres and
  centimetres/second. They are converted to ENU metres and metres/second; z is
  not negated. `navFlags` supplies navigation validity.
- MAVLink NED coordinates are converted to ENU. Supported ODOMETRY parent frames
  are LOCAL_NED and LOCAL_ENU; BODY_FRD velocity is rotated with the recorded
  quaternion. Unsupported local frames remain in additional source records.
- Canonical MAVLink trajectories use one message/system/component channel,
  selected by observation count among supported frames. Canonical DataFlash
  trajectories use one EKF family/core. Alternatives are retained in raw groups
  so separate estimators or vehicles are not merged into one ML trajectory.
- DataFlash BCL integer cell voltages are millivolts; 0/65535 unavailable entries
  are excluded. RemPct is always a percentage: 1 means 1%, not 100%.
- RADIO_STATUS `txbuf` is free transmit-buffer percentage, not an overrun
  count. `rxerrors` and `fixed` are separate counters. SYS_STATUS communication
  errors are not reported as proven lost messages, and drop rate uses a 0–1
  fraction. RC radio loss is distinguished from a GCS connection failure.
- EmuFlight engineering-unit conversions still require verified scales where
  units vary. `EmuFlightUnitConfig` supports explicit scales. Unconverted raw
  readings are retained instead of supplying guessed volts or metres.

## Evidence retained outside the common scalar fields

`additional_data` carries:

- `extraction_coverage`: per-category counts, field-population counts, recorded
  versus expected sources, unsupported-category explanations, and incomplete
  decoding flags.
- `message_inventory`: observed message/frame counts and field names.
- `source_record_groups`: decoded observations not covered by common scalar
  fields. DataFlash retains decoded source records, including IMU, attitude,
  RC input/output, estimator and mission-related records. Blackbox retains all
  accepted main, GPS, home, slow and event frames. MAVLink retains every decoded
  packet, including repeated heartbeats, attitude, IMU, actuator, RC, mission and
  alternative estimator observations, even when normalization reports state
  changes rather than every repeated sample.
- DataFlash `schema_history` and `decode_stats`: FMT definitions are applied in
  source order, including redefinitions of a message ID. Unsupported/inconsistent
  definitions, decoding errors and truncation are reported.
- Blackbox `blackbox_logs`: per-session headers, file offsets and decoder
  diagnostics, including rejected frames, resynchronization, missing history,
  truncation, and unsupported encoding samples. Concatenated sessions remain
  separately identified.

Decoded source records retain native values and offsets/log or sender identity
where available. Unknown units stay native. JSON uses null for nonfinite numeric
values; the hashed source file and offsets remain the original byte-level
reference. The decoder does not fabricate samples from damaged bytes.

## CLI and JSON reporting

Run from the project root:

```bash
.venv/bin/python -m cli.main normalized-analysis \
  --input path/to/evidence.bin \
  --output reports/CASE/report.json
```

The registry chooses the parser for supported `.ulg`, DataFlash binary logs,
MAVLink `.tlog`, or supported Blackbox logs. The terminal summary includes all
normalized categories. JSON includes all category counts, complete normalized
record fields and raw provenance, extraction coverage, additional decoded
observations, analysis/findings, and evidence/report hashes. The report JSON's
SHA-256 is stored alongside it as `report.json.sha256`.

Coverage status meanings:

| Status | Meaning |
| --- | --- |
| `extracted` | Normalized records were produced; inspect field counts for populated values |
| `not_recorded` | No applicable decoded source or requisite fields were observed |
| `source_present_no_normalized_records` | Source observations exist but no normalized record was produced; inspect unit/configuration and raw observations |
| `unsupported` | The adapter explicitly identifies a category with no supported protocol representation |
| `decode_incomplete` | No normalized records were produced and decoding diagnostics show missing/damaged/unsupported data |

`decoder_incomplete` can also be true when some records were successfully
extracted. An inventory of accepted records does not establish that a damaged
source was completely recovered.

## Validation

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests
```

Existing fixtures and regression tests are supplemented by wire-level fixtures
for MAVLink 2 ODOMETRY/PARAM_EXT, secondary GPS, estimator/fence health, radio
counters, DataFlash EKF/cell/failsafe data, FMT changes and truncation, and
Betaflight/INAV/EmuFlight I/P/S/E decoding with sensor and control data.

These synthetic fixtures validate the mappings and integration. They do not
establish support for every firmware revision or vendor extension; real-log
validation remains important, particularly for Blackbox unit conventions.

## Format references

- [MAVLink common messages and coordinate frames](https://mavlink.io/en/messages/common.html)
- [ArduPilot EKF log definitions](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_NavEKF3/LogStructure.h)
- [ArduPilot filter-status flags](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_NavEKF/AP_Nav_Common.h)
- [ArduPilot explicit error/failsafe codes](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_Logger/AP_Logger.h)
- [ArduPilot battery log units](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_BattMonitor/AP_BattMonitor_Logging.cpp)
- [Betaflight Blackbox field definitions](https://github.com/betaflight/betaflight/blob/4.5.0/src/main/blackbox/blackbox.c)
- [INAV Blackbox field definitions](https://github.com/iNavFlight/inav/blob/7.1.0/src/main/blackbox/blackbox.c)
- [INAV navigation validity](https://github.com/iNavFlight/inav/blob/master/src/main/navigation/navigation.c)
