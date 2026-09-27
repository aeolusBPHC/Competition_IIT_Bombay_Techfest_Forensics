import json
import html
from pathlib import Path
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

CASE_ID = "CASE-001"
EVIDENCE_ID = "EVD-20260919-175126"

EVIDENCE_DIR = (
    BASE_DIR
    / "repository"
    / "cases"
    / CASE_ID
    / EVIDENCE_ID
)

ANALYSIS_DIR = EVIDENCE_DIR / "analysis"

OUTPUT_FILE = BASE_DIR / "reporting" / "forensic_report.html"


# ============================================================
# FILE HELPERS
# ============================================================

def load_json(filename):
    path = ANALYSIS_DIR / filename

    if not path.exists():
        return {
            "_missing": True,
            "_filename": filename
        }

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        return {
            "_error": str(exc),
            "_filename": filename
        }


def load_root_json(filename):
    path = EVIDENCE_DIR / filename

    if not path.exists():
        return {
            "_missing": True,
            "_filename": filename
        }

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        return {
            "_error": str(exc),
            "_filename": filename
        }


def esc(value):
    return html.escape(str(value))


# ============================================================
# GENERIC JSON HTML RENDERER
# ============================================================

def render_value(value, level=0):
    if value is None:
        return '<span class="null">null</span>'

    if isinstance(value, bool):
        return (
            '<span class="bool">true</span>'
            if value
            else '<span class="bool">false</span>'
        )

    if isinstance(value, (int, float)):
        return f'<span class="number">{esc(value)}</span>'

    if isinstance(value, str):
        return f'<span class="string">{esc(value)}</span>'

    if isinstance(value, list):
        if not value:
            return "<em>None</em>"

        items = []
        for item in value:
            items.append(
                f'<li>{render_value(item, level + 1)}</li>'
            )

        return "<ul>" + "".join(items) + "</ul>"

    if isinstance(value, dict):
        rows = []

        for key, val in value.items():
            rows.append(
                "<tr>"
                f"<th>{esc(key)}</th>"
                f"<td>{render_value(val, level + 1)}</td>"
                "</tr>"
            )

        return (
            '<table class="nested-table">'
            "<tbody>"
            + "".join(rows)
            + "</tbody>"
            "</table>"
        )

    return esc(value)


# ============================================================
# SECTION HELPERS
# ============================================================

def section(title, content):
    return f"""
    <section>
        <h2>{esc(title)}</h2>
        {content}
    </section>
    """


def info_table(data):
    rows = []

    for key, value in data.items():
        rows.append(
            "<tr>"
            f"<th>{esc(key)}</th>"
            f"<td>{render_value(value)}</td>"
            "</tr>"
        )

    return (
        '<table class="info-table">'
        "<tbody>"
        + "".join(rows)
        + "</tbody>"
        "</table>"
    )


def status_badge(text, css_class="info"):
    return f'<span class="badge {css_class}">{esc(text)}</span>'


# ============================================================
# EVIDENCE SUMMARY
# ============================================================

def build_evidence_summary(metadata, custody):
    rows = []

    if isinstance(metadata, dict):
        for key in [
            "case_id",
            "evidence_id",
            "source_file",
            "original_filename",
            "original_size_bytes",
            "sha256",
            "verified"
        ]:
            if key in metadata:
                rows.append(
                    "<tr>"
                    f"<th>{esc(key)}</th>"
                    f"<td>{render_value(metadata[key])}</td>"
                    "</tr>"
                )

    return (
        '<table class="info-table">'
        "<tbody>"
        + "".join(rows)
        + "</tbody>"
        "</table>"
    )


# ============================================================
# SECURITY INDICATORS
# ============================================================

def build_security_indicators(data):
    if not isinstance(data, dict):
        return "<p>No security-indicator data available.</p>"

    indicators = data.get("indicators", [])

    if not indicators:
        return "<p>No indicators recorded.</p>"

    rows = []

    for indicator in indicators:
        severity = indicator.get("severity", "UNKNOWN")

        severity_class = severity.lower()

        rows.append(
            "<tr>"
            f"<td>{esc(indicator.get('timestamp_seconds', 'N/A'))}</td>"
            f"<td>{esc(indicator.get('category', ''))}</td>"
            f"<td>{status_badge(severity, severity_class)}</td>"
            f"<td><strong>{esc(indicator.get('indicator_type', ''))}</strong>"
            f"<br>{esc(indicator.get('description', ''))}</td>"
            f"<td>{esc(indicator.get('confidence', ''))}</td>"
            "</tr>"
        )

    return f"""
    <div class="summary-cards">

        <div class="card">
            <div class="card-number">
                {esc(data.get("indicator_count", len(indicators)))}
            </div>
            <div class="card-label">Indicators</div>
        </div>

        <div class="card">
            <div class="card-number">
                {esc(data.get("severity_counts", {}).get("MEDIUM", 0))}
            </div>
            <div class="card-label">Medium</div>
        </div>

        <div class="card">
            <div class="card-number">
                {esc(data.get("severity_counts", {}).get("LOW", 0))}
            </div>
            <div class="card-label">Low</div>
        </div>

        <div class="card">
            <div class="card-number">
                {esc(data.get("severity_counts", {}).get("INFO", 0))}
            </div>
            <div class="card-label">Informational</div>
        </div>

    </div>

    <table class="data-table">
        <thead>
            <tr>
                <th>Time (s)</th>
                <th>Category</th>
                <th>Severity</th>
                <th>Indicator / Observation</th>
                <th>Confidence</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows)}
        </tbody>
    </table>
    """


# ============================================================
# COMMAND ANALYSIS
# ============================================================

def build_command_summary(command_data, ack_data):
    content = ""

    if isinstance(command_data, dict):
        content += "<h3>Vehicle Command Analysis</h3>"
        content += info_table(command_data)

    if isinstance(ack_data, dict):
        content += "<h3>Command / ACK Matching</h3>"
        content += info_table(ack_data)

    return content


# ============================================================
# STATE ANALYSIS
# ============================================================

def build_state_summary(state_data):
    if not isinstance(state_data, dict):
        return "<p>No state reconstruction data available.</p>"

    content = ""

    initial_status = state_data.get("initial_vehicle_status")

    if initial_status:
        content += "<h3>Initial Vehicle State</h3>"
        content += info_table(initial_status)

    initial_land = state_data.get("initial_land_detection")

    if initial_land:
        content += "<h3>Initial Land Detection State</h3>"
        content += info_table(initial_land)

    events = state_data.get("events", [])

    if events:
        rows = []

        for event in events:
            rows.append(
                "<tr>"
                f"<td>{esc(event.get('timestamp_seconds', ''))}</td>"
                f"<td>{esc(event.get('event_type', ''))}</td>"
                f"<td>{esc(event.get('previous_value', ''))}</td>"
                f"<td>{esc(event.get('new_value', ''))}</td>"
                "</tr>"
            )

        content += """
        <h3>State Transition Events</h3>

        <table class="data-table">
            <thead>
                <tr>
                    <th>Time (s)</th>
                    <th>Event</th>
                    <th>Previous</th>
                    <th>New</th>
                </tr>
            </thead>
            <tbody>
        """

        content += "".join(rows)

        content += """
            </tbody>
        </table>
        """

    return content


# ============================================================
# TIMELINE
# ============================================================

def build_timeline(data):
    if not isinstance(data, dict):
        return "<p>No timeline available.</p>"

    events = data.get("events", [])

    if not events:
        return "<p>No timeline events available.</p>"

    rows = []

    for event in events:
        rows.append(
            "<tr>"
            f"<td>{esc(event.get('timestamp_seconds', ''))}</td>"
            f"<td>{esc(event.get('event_type', ''))}</td>"
            f"<td>{render_value(event.get('details', {}))}</td>"
            "</tr>"
        )

    return f"""
    <p>Total reconstructed events: <strong>{len(events)}</strong></p>

    <table class="data-table">
        <thead>
            <tr>
                <th>Time (s)</th>
                <th>Event Type</th>
                <th>Details</th>
            </tr>
        </thead>

        <tbody>
            {"".join(rows)}
        </tbody>
    </table>
    """


# ============================================================
# HTML GENERATION
# ============================================================

def generate_report():

    metadata = load_root_json("metadata.json")
    custody = load_root_json("chain_of_custody.json")

    navigation = load_json("navigation_integrity.json")
    commands = load_json("command_forensics.json")
    ack_matching = load_json("command_ack_matching.json")
    states = load_json("state_reconstruction.json")
    timeline = load_json("forensic_timeline.json")
    correlations = load_json("event_correlations.json")
    security = load_json("security_indicators.json")

    generated_time = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # --------------------------------------------------------
    # CASE INFORMATION
    # --------------------------------------------------------

    case_info = {
        "Case ID": CASE_ID,
        "Evidence ID": EVIDENCE_ID,
        "Source": "17_02_27.ulg",
        "Report generated": generated_time,
    }

    # --------------------------------------------------------
    # LOG SUMMARY
    # --------------------------------------------------------

    log_summary = {}

    if isinstance(navigation, dict):
        log_summary["GPS samples"] = navigation.get(
            "sample_count", "N/A"
        )

    if isinstance(commands, dict):
        log_summary["Vehicle commands"] = commands.get(
            "command_count",
            commands.get("commands_count", "N/A")
        )

    if isinstance(ack_matching, dict):
        log_summary["Command ACKs"] = ack_matching.get(
            "ack_count",
            ack_matching.get("acks_count", "N/A")
        )

    if isinstance(states, dict):
        log_summary["State events"] = states.get(
            "event_count", "N/A"
        )

    if isinstance(timeline, dict):
        log_summary["Timeline events"] = len(
            timeline.get("events", [])
        )

    # --------------------------------------------------------
    # SECURITY CONCLUSION
    # --------------------------------------------------------

    conclusion = """
    <div class="notice">

        <strong>Evidence interpretation:</strong>

        The findings in this report represent observations
        reconstructed from the analyzed PX4 ULog and associated
        forensic artifacts.

        Security indicators identify conditions that may warrant
        further investigation. They do not, by themselves,
        establish malicious intent, unauthorized access, or the
        occurrence of a cyberattack.

        Recorded GPS spoofing/jamming fields, GCS connection
        transitions, command-origin fields, command/ACK
        relationships, and failsafe states are reported as
        observed telemetry conditions.

        Temporal proximity between events is not treated as proof
        of causality.

    </div>
    """

# --------------------------------------------------------
# VISUALIZATION SECTION
# --------------------------------------------------------

PLOTS_DIR = BASE_DIR / "reporting" / "plots"


def image_if_exists(filename, title):

    path = PLOTS_DIR / filename

    if not path.exists():
        return f"""
        <div class="notice">
            Visualization unavailable: {esc(filename)}
        </div>
        """

    # Relative path from reporting/forensic_report.html
    relative_path = f"plots/{filename}"

    return f"""
    <div class="plot-container">

        <h3>{esc(title)}</h3>

        <img
            src="{esc(relative_path)}"
            alt="{esc(title)}"
            class="forensic-plot"
        >

    </div>
    """


visualization_section = (
    image_if_exists(
        "gps_flight_path.png",
        "GPS Flight Path"
    )

    + image_if_exists(
        "altitude_speed_timeline.png",
        "Altitude and Speed Timeline"
    )

    + image_if_exists(
        "security_indicator_timeline.png",
        "Security Indicator Timeline"
    )
)
    # --------------------------------------------------------
    # HTML DOCUMENT
    # --------------------------------------------------------

html_document = f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>
Drone Forensic Report - {esc(CASE_ID)}
</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    font-family: Arial, Helvetica, sans-serif;
    background: #f4f6f8;
    color: #20252b;
    line-height: 1.5;
}}

.container {{
    max-width: 1400px;
    margin: auto;
    padding: 30px;
}}

header {{
    background: #17202a;
    color: white;
    padding: 35px;
    border-radius: 10px;
    margin-bottom: 25px;
}}

header h1 {{
    margin: 0 0 10px 0;
    font-size: 30px;
}}

header p {{
    margin: 4px 0;
    opacity: 0.9;
}}

section {{
    background: white;
    margin-bottom: 25px;
    padding: 25px;
    border-radius: 10px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}}

h2 {{
    border-bottom: 2px solid #dfe4e8;
    padding-bottom: 10px;
    margin-top: 0;
}}

h3 {{
    margin-top: 25px;
}}

.info-table,
.data-table,
.nested-table {{
    width: 100%;
    border-collapse: collapse;
}}

.info-table th,
.info-table td,
.data-table th,
.data-table td,
.nested-table th,
.nested-table td {{
    border: 1px solid #dfe4e8;
    padding: 9px;
    text-align: left;
    vertical-align: top;
}}

.info-table th {{
    width: 280px;
    background: #f1f3f5;
}}

.data-table th {{
    background: #e9ecef;
}}

.data-table tr:nth-child(even) {{
    background: #f8f9fa;
}}

.nested-table {{
    margin: 5px 0;
}}

.nested-table th {{
    width: 200px;
    background: #f5f5f5;
}}

.summary-cards {{
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(180px, 1fr));
    gap: 15px;
    margin-bottom: 25px;
}}

.card {{
    background: #f8f9fa;
    border: 1px solid #dfe4e8;
    border-radius: 8px;
    padding: 20px;
    text-align: center;
}}

.card-number {{
    font-size: 30px;
    font-weight: bold;
}}

.card-label {{
    color: #687078;
}}

.badge {{
    display: inline-block;
    padding: 3px 9px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: bold;
}}

.badge.info {{
    background: #e8f1f8;
    color: #24506b;
}}

.badge.low {{
    background: #f5f0df;
    color: #68571e;
}}

.badge.medium {{
    background: #f4e6d8;
    color: #754318;
}}

.badge.high {{
    background: #f0dcdc;
    color: #7a2222;
}}

.plot-container {
    margin: 30px 0;
    padding: 15px;
    border: 1px solid #dfe4e8;
    border-radius: 8px;
    background: #fafbfc;
}

.forensic-plot {
    display: block;
    width: 100%;
    max-width: 1100px;
    height: auto;
    margin: 15px auto;
    border: 1px solid #dfe4e8;
}

.notice {{
    background: #f8f9fa;
    border-left: 5px solid #59636e;
    padding: 18px;
    margin: 15px 0;
}}

.null {{
    color: #888;
}}

.string {{
    color: #24506b;
}}

.number {{
    color: #5a3d8e;
}}

.bool {{
    color: #47733d;
}}

footer {{
    text-align: center;
    color: #687078;
    padding: 20px;
}}

@media print {{

    body {{
        background: white;
    }}

    section {{
        box-shadow: none;
        border: 1px solid #ddd;
        break-inside: avoid;
    }}

    header {{
        color: black;
        background: white;
        border: 2px solid #222;
    }}

}}

</style>

</head>

<body>

<div class="container">

<header>

<h1>Drone Forensic Examination Report</h1>

<p>
<strong>Case:</strong> {esc(CASE_ID)}
</p>

<p>
<strong>Evidence:</strong> {esc(EVIDENCE_ID)}
</p>

<p>
<strong>Source:</strong> 17_02_27.ulg
</p>

<p>
<strong>Generated:</strong> {esc(generated_time)}
</p>

</header>


{section(
    "1. Case Information",
    info_table(case_info)
)}


{section(
    "2. Evidence Integrity",
    build_evidence_summary(metadata, custody)
)}


{section(
    "3. Evidence Chain of Custody",
    render_value(custody)
)}


{section(
    "4. Flight / Telemetry Summary",
    info_table(log_summary)
)}


{section(
    "5. Navigation Analysis",
    render_value(navigation)
)}

{section(
    "6. Forensic Visualizations",
    visualization_section
)}


{section(
    "7. Command and ACK Forensics",
    build_command_summary(commands, ack_matching)
)}


{section(
    "8. State Reconstruction",
    build_state_summary(states)
)}


{section(
    "9. Event Correlation",
    render_value(correlations)
)}


{section(
    "10. Security Indicators",
    build_security_indicators(security)
)}


{section(
    "11. Forensic Timeline",
    build_timeline(timeline)
)}


{section(
    "12. Evidence-Based Interpretation",
    conclusion
)}


{section(
    "13. Analyst Notes and Limitations",
    """
    <ul>
        <li>
            Findings are based on the available PX4 ULog evidence.
        </li>

        <li>
            Absence of a recorded indicator does not prove absence
            of an underlying event.
        </li>

        <li>
            GPS spoofing and jamming fields are treated as recorded
            telemetry observations.
        </li>

        <li>
            GCS connection loss is reported as a communication-state
            transition and is not automatically classified as a
            cyberattack.
        </li>

        <li>
            Command/ACK matching uses command identifiers and must
            be distinguished from simple temporal proximity.
        </li>

        <li>
            The report does not infer malicious intent from telemetry
            alone.
        </li>

        <li>
            Severity values are analytical classifications generated
            by the toolkit and should be interpreted together with
            the underlying evidence.
        </li>
    </ul>
    """
)}


<footer>

Drone Forensics Toolkit<br>
Automated forensic report generated from PX4 evidence

</footer>

</div>

</body>

</html>
"""

 OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(html_document)

    print("=" * 70)
    print("PX4 AUTOMATED FORENSIC REPORT")
    print("=" * 70)
    print()
    print(f"Case:       {CASE_ID}")
    print(f"Evidence:   {EVIDENCE_ID}")
    print()
    print("Report generated:")
    print(OUTPUT_FILE)
    print()
    print("Report size:")
    print(f"{OUTPUT_FILE.stat().st_size:,} bytes")
    print()
    print("STATUS: SUCCESS")
    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    generate_report()
