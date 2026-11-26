"""Download seven attributed Pixhawk 6C Mini logs and verify their reports."""
import hashlib
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
LOGS = [
    ("attitude_failsafe", "66f67982-c85d-45d2-806e-dbfab3cc2f94", 28146522,
     "Attitude / roll failsafe", "https://discuss.px4.io/t/preflight-fail-attitude-failure-roll-message/45883"),
    ("offboard_no_gps", "7207702f-978c-4716-a085-ba166e31d8ac", 7873000,
     "Offboard altitude loss; optical flow, no GPS", "https://discuss.px4.io/t/vehicle-doesnt-preserve-its-height-in-offboard-mode/43053"),
    ("motor_oscillation", "3383e1f8-d744-435b-957f-1f6b9536f50e", 3425170,
     "Motor oscillation and overheating", "https://discuss.px4.io/t/px4-v1-14-3-blheli-32-strange-motor-output-and-overheating/40495"),
    ("land_mode", "4e063d14-3b85-4a2e-a357-81b2e83268a3", 3938455,
     "Unexpected movement in Land mode", "https://discuss.px4.io/t/land-mode-and-commander-land-making-the-vehicle-return-to-launch/40389"),
    ("battery_original", "ae39b926-bb41-4077-baa0-5b3a9b10b659", 5549240,
     "Battery status investigation: original power module", "https://discuss.px4.io/t/pixhawk-6c-mini-battery-status-dropping-out-during-flight/48044"),
    ("battery_comparison", "0be6e144-0956-49c4-a30e-e19e16ad5c65", 4830027,
     "Battery status investigation: comparison power module", "https://discuss.px4.io/t/pixhawk-6c-mini-battery-status-dropping-out-during-flight/48044"),
    ("ekf_altitude", "be8dbf81-68c4-48e0-b559-cbadcf979396", 2980895,
     "EKF altitude estimation discrepancy", "https://discuss.px4.io/t/ekf2-altitude-offset/49379"),
]


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def download(spec):
    slug, log_id, expected_size, title, source = spec
    target = ROOT / "repository/public_logs/pixhawk6c_mini" / f"{slug}.ulg"
    target.parent.mkdir(parents=True, exist_ok=True)
    url = "https://review.px4.io/download?log=" + log_id
    if not target.exists():
        partial = target.with_suffix(".ulg.part")
        with urlopen(Request(url, headers={"User-Agent": "DroneForensics/1.0"}), timeout=120) as response:
            with partial.open("wb") as stream:
                while block := response.read(1024 * 1024):
                    stream.write(block)
        if partial.stat().st_size != expected_size:
            raise ValueError(f"Incomplete download: {slug}: {partial.stat().st_size} != {expected_size}")
        partial.rename(target)
    with target.open("rb") as stream:
        valid = stream.read(7) == b"ULog\x01\x12\x35"
    if target.stat().st_size != expected_size or not valid:
        raise ValueError(f"Invalid existing download: {target}")
    result = {"slug": slug, "log_id": log_id, "reported_case": title,
              "hardware_attribution": "Pixhawk 6C Mini, as stated by the uploader",
              "source_post": source, "download_url": url,
              "path": str(target), "size_bytes": target.stat().st_size,
              "sha256": digest(target), "download_checked_utc": datetime.now(timezone.utc).isoformat()}
    print(f"DOWNLOADED {slug}: {result['size_bytes']} bytes", flush=True)
    return result


def write_index(folder, rows):
    def link(path, label):
        relative = os.path.relpath(path, folder)
        return f'<a href="{html.escape(relative, quote=True)}">{html.escape(label)}</a>'
    table = []
    for row in rows:
        counts = row.get("record_counts", {})
        output = folder / row["slug"]
        report = link(output / "forensic_report.html", "HTML report") if row["status"] == "passed" else html.escape(row.get("error", "Failed"))
        if row.get("ml_status") == "passed":
            report += "<br>" + link(row["ml_report"], "GRU ML report")
        table.append(f'<tr><td>{html.escape(row["reported_case"])}</td><td>{row["status"]}</td>'
                     f'<td>{counts.get("gps", "—")}</td><td>{counts.get("trajectory", "—")}</td>'
                     f'<td>{row.get("findings_count", "—")}</td><td>{row.get("plot_count", "—")}</td>'
                     f'<td>{report}<br>{link(row["path"], "Source log")}<br>'
                     f'{link(output / "pipeline.log", "Processing log")}</td></tr>')
    passed = sum(row["status"] == "passed" for row in rows)
    ml_count = sum(row.get("ml_status") == "passed" for row in rows)
    ml_note = (f"{ml_count} GRU forecast appendices are available. These use a previously trained checkpoint; "
               "predictions are estimates, and the checkpoint validation-selected baseline is identified in each appendix."
               if ml_count else "No compatible model checkpoint was supplied, so trajectory forecasting was not requested.")
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Pixhawk 6C Mini — forensic reports</title>
<style>body{{font:16px system-ui;max-width:1200px;margin:40px auto;padding:0 20px;color:#17243b;background:#f8fafc}}table{{border-collapse:collapse;width:100%;background:white}}th,td{{padding:14px;border:1px solid #dce3ed;text-align:left}}th{{background:#e8eff8}}a{{color:#1759b3}}p{{line-height:1.6}}</style>
<h1>Pixhawk 6C Mini: public flight-log reports</h1><p>{passed} of {len(rows)} logs passed acquisition, parsing, report generation and artifact hash verification.</p>
<p>Cases are labeled using the uploaders' descriptions. These labels do not establish the cause of an incident. No media input was supplied. {ml_note}</p>
<table><thead><tr><th>Reported case</th><th>Validation</th><th>GPS records</th><th>Trajectory records</th><th>Findings</th><th>Plots</th><th>Files</th></tr></thead><tbody>{''.join(table)}</tbody></table>
<p><a href="batch_results.json">Validation results and source references (JSON)</a></p></html>'''
    (folder / "index.html").write_text(page, encoding="utf-8")


def main():
    with ThreadPoolExecutor(max_workers=3) as pool:
        sources = list(pool.map(download, LOGS))
    source_manifest = ROOT / "repository/public_logs/pixhawk6c_mini/sources.json"
    source_manifest.write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    batch = ROOT / "reports/pixhawk6c_mini" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    batch.mkdir(parents=True)
    results = []
    for number, source in enumerate(sources, 1):
        output = batch / source["slug"]
        console = batch / f"{source['slug']}.pipeline.log"
        command = [sys.executable, "-m", "cli.main", "process", "--input", source["path"],
                   "--case", "PUBLIC-6CMINI-" + source["slug"].upper().replace("_", "-"),
                   "--output", str(output)]
        started = time.monotonic()
        row = dict(source, command=command, status="failed")
        print(f"PROCESSING {number}/{len(sources)} {source['slug']}", flush=True)
        try:
            env = dict(os.environ, MPLBACKEND="Agg", PYTHONUNBUFFERED="1")
            with console.open("w") as stream:
                run = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
            if run.returncode:
                raise RuntimeError(f"Process exited {run.returncode}; see {console}")
            manifest = json.loads((output / "run_manifest.json").read_text())
            assert manifest["status"] == "complete"
            assert manifest["log_integrity_reverified"]
            assert digest(source["path"]) == source["sha256"] == manifest["log_sha256"]
            assert digest(manifest["acquired_log"]) == source["sha256"]
            for relative, expected in manifest["sha256"].items():
                assert digest(output / relative) == expected, relative
            for name in ("normalized_report.json", "forensic_report.html", "run_manifest.json"):
                expected = (output / (name + ".sha256")).read_text().split()[0]
                assert digest(output / name) == expected, name
            report = json.loads((output / "normalized_report.json").read_text())
            assert report["evidence"]["platform"] == "PX4"
            row.update(status="passed", record_counts=report["record_counts"],
                       findings_count=len(report.get("findings", [])),
                       plot_count=len(list((output / "forensic_report_plots").glob("*.png"))),
                       artifact_hashes_verified=len(manifest["sha256"]),
                       report=str(output / "forensic_report.html"),
                       evidence_id=manifest["evidence_id"])
            del report
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["elapsed_s"] = round(time.monotonic() - started, 2)
        output.mkdir(exist_ok=True)
        if console.exists():
            console.rename(output / "pipeline.log")
        results.append(row)
        (batch / "batch_results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        write_index(batch, results)
        print(f"{row['status'].upper()} {source['slug']}: {row['elapsed_s']} s", flush=True)
    print(f"REPORT INDEX: {batch / 'index.html'}", flush=True)
    return 0 if all(row["status"] == "passed" for row in results) else 1


if __name__ == "__main__":
    sys.exit(main())
