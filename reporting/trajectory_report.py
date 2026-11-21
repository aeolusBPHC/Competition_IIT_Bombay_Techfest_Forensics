"""A forecast appendix that cannot be mistaken for recovered flight evidence."""
from __future__ import annotations

import html
import json
from pathlib import Path


def generate_trajectory_report(result, output):
    forecast = result["forecast"]
    rows = "\n".join(
        f"<tr><td>{time:.6f}</td><td>{point[0]:.4f}</td>"
        f"<td>{point[1]:.4f}</td><td>{point[2]:.4f}</td></tr>"
        for time, point in zip(forecast["timestamps_s"], forecast["positions_m"])
    )
    title = html.escape(str(result.get("case_id") or "Trajectory forecast"))
    provenance = html.escape(json.dumps({"source": result["source"], "model": result["model"],
                                        "provenance": result["provenance"]}, indent=2))
    history = html.escape(json.dumps(result["observed_history"], indent=2))
    page = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><title>{title} — forecast estimates</title>
<style>body{{font:16px system-ui;max-width:1000px;margin:40px auto;padding:0 20px;color:#182534}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:10px;text-align:right;border-bottom:1px solid #ccd4dd}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f4f8;padding:16px}}
.notice{{border-left:5px solid #b7791f;background:#fff8e8;padding:16px}}</style>
<h1>{title}</h1><p class="notice"><strong>Predicted trajectory — model estimates, not recorded evidence.</strong>
This appendix extrapolates from observations ending at {forecast['cutoff_timestamp_s']:.6f} source seconds.
It does not establish where the aircraft subsequently flew.</p>
<p>Predictor: {html.escape(result['model']['predictor'])}. Positions use local ENU metres:
x east, y north, z up. Timestamps use the source log clock, not necessarily UTC.</p>
<p>{html.escape(forecast['uncertainty_note'])}</p>
<h2>Forecast estimates</h2><table><thead><tr><th>Source time (s)</th><th>East (m)</th>
<th>North (m)</th><th>Up (m)</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Observed history</h2><p>Values below are causal resamples of parsed observations.
The source evidence remains the authoritative record.</p><pre>{history}</pre>
<details><summary>Source and model provenance</summary><pre>{provenance}</pre></details></html>"""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    return output
