# Files to publish together

The live GitHub repository was checked at commit `59fdff5cb6bf31f7ff84782728e80e23aac9196b`.
The example reports and their corrected links are now published. Its main README
still describes local pipeline changes whose source/setup files are missing on
GitHub. Publishing the matching source changes makes the README consistent.

## Required source and setup files

- `README.md`
- `requirements.txt`
- `requirements-dev.txt`
- `acquisition/acquire.py`
- `cli/main.py`
- `cli/pipeline.py`
- `platform_parsers/mavlink/tlog_parser.py`
- `media/extractor.py`
- `reporting/evidence_gallery.py`
- `tests/test_cli_process.py`
- `tools/process_pixhawk6c_mini_logs.py`
- `tools/add_pixhawk6c_mini_ml_reports.py`
- `tools/publish_verified_updates.sh`
- `RECENT_CHANGES.md`
- `PUBLISHING_CHECKLIST.md`

`GITHUB_CHANGES_ONE_LINE_EACH.txt` is an optional history summary.
Use the current local files; the older root patch predates several later README
and ML-report updates. Select these paths explicitly rather than staging the
entire working directory.

## Reports to publish

Publish `reports/examples/pixhawk6c_mini/` as a complete directory. It contains:

- An index and a GitHub-readable README linking all seven examples.
- Each case's `forensic_report.html`, `ml_report.html`, `ml_predictions.json`, and `ml_forecast.png`.
- Fresh `.sha256` sidecars for the publication copies.
- Source URLs/hashes, a compact validation summary and a publication manifest.

For a root-level index, publish the corrected `pixhawk_examples.md` alongside
that directory. Its links include `reports/examples/pixhawk6c_mini/`. The
directory's own `README.md` uses shorter links relative to that directory;
moving only that README to the repository root breaks those paths. Uploading
only the Markdown page leaves its report targets missing as well.

These are publication derivatives: local path strings have been normalized,
and checksums were recalculated. Numerical observations and GRU predictions are
unchanged. Original reports and their integrity records remain in
`reports/pixhawk6c_mini/20261126-155443/`.

GitHub displays the Markdown index and PNG charts. Download the directory and
open `index.html` in a browser to view interactive HTML links; an HTML file in
the repository is normally shown as source on GitHub.

The source logs, acquisition copies, normalized JSON dumps, saved checkpoint,
processing logs, and duplicate pre-ML HTML are omitted from the compact examples.
Keep the complete original batch locally. Full reproduction additionally needs
the public source logs and a compatible model checkpoint. The original batch's
`models/gru_seed42.pt` can be distributed separately through Git LFS if desired;
it is not required to view the example reports.

`reports/regression-tests-summary.json` and `reports/regression-tests.xml` are
optional supporting validation artifacts. Avoid treating `run_manifest.json` as
a standalone publishable file when the files it hashes are omitted.

## What was wrong

1. The generic MAVLink module defined an ArduPilot class instead of `MAVLinkTLogParser`, preventing the parser registry from importing.
2. The original `process` command acquired evidence but left analysis and reporting as placeholders.
3. The published README referenced missing requirements files and CLI behavior that existed only in local changes.
4. Test logs were Git LFS pointers instead of their binary contents, causing invalid-header/empty-record failures; seven required fixtures have now been restored and SHA-256 verified locally.
5. One Python environment lacked PyTorch, preventing two ML test modules from being collected.
6. The initial seven-log batch omitted checkpoint inference; explicit GRU appendices have now been added to every case.

## Verified behavior and remaining conditions

- Local full suite: **287 passed, 15 skipped**; all **302 tests** collected.
- Independent serial README verification: new Python 3.12 virtual environment, fresh dependency installs, verified Git LFS objects, and the local fixes over GitHub commit `59fdff5`. Full suite **288 passed, 14 skipped**; after downloading media samples, media tests **55 passed, 1 skipped**.
- Seven real logs: forensic reports and GRU appendices generated and source/output hashes verified.
- Checkpoint/inference workflow tests: **6 passed**.
- README CLI interfaces are checked against the local implementation.
- A fresh clone of the current GitHub branch fails at `pip install -r requirements.txt` because that file is missing. The serial verification applies the listed source changes to an isolated clone and tests a new virtual environment; see `reports/readme-serial-verification.json` for the final outcome and dependency versions.
- After publishing the matching source changes, install dependencies in the intended Python 3.12 virtual environment, fetch Git LFS evidence, replace example input paths, use a new output folder, and provide a compatible checkpoint for forecasts.
- Optional media features depend on the installed external tools and their versions. External-sample tests can remain skipped.
- The installed ExifTool is 12.76; the README documents that DJI `djmd` decoding requires 13.05 or newer. This does not prevent the tested image/media commands from running, but it limits that specific telemetry decoder.

No changes have been pushed by the assistant.

## One-command update

After reviewing the listed files, run this command yourself from the local review checkout:

```bash
bash tools/publish_verified_updates.sh
```

The script creates a new worktree from the latest `origin/main`, copies only the
curated source/docs/validation files, commits them, and pushes `HEAD:main` using
your Git credentials. It preserves the existing report publication and excludes
raw logs, duplicated acquisitions, virtual environments and temporary test data.
It uses a normal push and will stop if Git rejects it. To inspect the file list
without publishing, pass `--dry-run`.
