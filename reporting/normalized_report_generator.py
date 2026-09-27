import argparse
import html
import json
import base64
from pathlib import Path
from datetime import datetime
from platform_parsers.common.registry import ParserRegistry
from reporting.normalized_visualize import generate_visualizations

# ============================================================
# HELPERS
# ============================================================

def esc(value):
    return html.escape(str(value))


def load_json(path):
    path = Path(path)

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fmt(value):
    if value is None:
        return "N/A"

    if isinstance(value, float):
        return f"{value:.3f}"

    return value


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


def render_value(value):

    if value is None:
        return '<span class="null">N/A</span>'

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
                f"<li>{render_value(item)}</li>"
            )

        return "<ul>" + "".join(items) + "</ul>"

    if isinstance(value, dict):

        rows = []

        for key, val in value.items():
            rows.append(
                "<tr>"
                f"<th>{esc(key)}</th>"
                f"<td>{render_value(val)}</td>"
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


def status_badge(text, css_class="info"):
    return (
        f'<span class="badge {css_class}">'
        f'{esc(text)}'
        f'</span>'
    )



def image_data_uri(image_path):
    """
    Convert a PNG image into a self-contained data URI.

    This allows the generated HTML report to contain the
    visualization directly without depending on external
    image files.
    """

    path = Path(image_path)

    if not path.is_file():
        return None

    encoded = base64.b64encode(
        path.read_bytes()
    ).decode("ascii")

    return f"data:image/png;base64,{encoded}"


def build_visualization_image(
    image_path,
    title,
    description=None,
):
    """
    Render one visualization as an embedded HTML figure.
    """

    data_uri = image_data_uri(image_path)

    if not data_uri:
        return ""

    description_html = ""

    if description:
        description_html = (
            f'<p class="plot-description">'
            f'{esc(description)}'
            f'</p>'
        )

    return f"""
    <div class="plot-card">

        <h3>{esc(title)}</h3>

        {description_html}

        <img
            class="forensic-plot"
            src="{data_uri}"
            alt="{esc(title)}"
        />

    </div>
    """


def build_visualizations(
    visualization_result,
    titles=None,
):
    """
    Build the HTML visualization section from the output of
    generate_visualizations().
    """

    titles = titles or {}

    generated = visualization_result.get(
        "generated",
        {},
    )

    unavailable = visualization_result.get(
        "unavailable",
        {},
    )

    content = ""

    for key, image_path in generated.items():

        title = titles.get(
            key,
            key.replace("_", " ").title(),
        )

        content += build_visualization_image(
            image_path,
            title,
        )

    if unavailable:

        rows = []

        for key, reason in unavailable.items():

            title = titles.get(
                key,
                key.replace("_", " ").title(),
            )

            rows.append(
                "<tr>"
                f"<td><strong>{esc(title)}</strong></td>"
                f"<td>{esc(reason)}</td>"
                "</tr>"
            )

        if rows:

            content += """
            <h3>Unavailable Visualizations</h3>

            <table class="data-table">

                <thead>
                    <tr>
                        <th>Visualization</th>
                        <th>Reason</th>
                    </tr>
                </thead>

                <tbody>
            """

            content += "".join(rows)

            content += """
                </tbody>

            </table>
            """

    if not content:
        return (
            "<p>No normalized visualizations were available "
            "for this evidence.</p>"
        )

    return content


# ============================================================
# EVIDENCE SUMMARY
# ============================================================

def build_record_summary(record_counts):

    labels = {
        "gps": "GPS Records",
        "commands": "Vehicle Commands",
        "command_acks": "Command ACKs",
        "states": "State Records",
        "parameters": "Parameter Records",
        "events": "Native Events",
    }

    cards = []

    for key, label in labels.items():
        cards.append(
            f"""
            <div class="card">
                <div class="card-number">
                    {esc(record_counts.get(key, 0))}
                </div>
                <div class="card-label">
                    {esc(label)}
                </div>
            </div>
            """
        )

    return (
        '<div class="summary-cards">'
        + "".join(cards)
        + "</div>"
    )


# ============================================================
# ANALYSIS SUMMARIES
# ============================================================

def build_analysis_summary(analysis):

    rows = []

    sections = [
        ("gps", "GPS"),
        ("navigation", "Navigation"),
        ("battery", "Battery"),
        ("telemetry", "Telemetry"),
        ("failsafe", "Failsafe"),
        ("states", "States"),
        ("parameters", "Parameters"),
        ("events", "Events"),
    ]

    for key, label in sections:

        data = analysis.get(key, {})

        if not isinstance(data, dict):
            continue

        count = (
            data.get("record_count")
            or data.get("sample_count")
            or data.get("state_count")
            or data.get("parameter_count")
            or data.get("event_count")
            or 0
        )

        available = data.get("available", True)

        rows.append(
            "<tr>"
            f"<td><strong>{esc(label)}</strong></td>"
            f"<td>{esc(count)}</td>"
            f"<td>{status_badge('AVAILABLE' if available else 'NOT AVAILABLE', 'info' if available else 'low')}</td>"
            "</tr>"
        )

    return f"""
    <table class="data-table">

        <thead>
            <tr>
                <th>Evidence Category</th>
                <th>Records</th>
                <th>Status</th>
            </tr>
        </thead>

        <tbody>
            {"".join(rows)}
        </tbody>

    </table>
    """


# ============================================================
# NAVIGATION
# ============================================================

def build_navigation(analysis):

    navigation = analysis.get("navigation", {})

    if not navigation:
        return "<p>No navigation analysis available.</p>"

    data = {
        "Available": navigation.get("available"),
        "Navigation records": navigation.get("record_count"),
        "Dead-reckoning records": navigation.get("dead_reckoning_count"),
        "Time range": navigation.get("time_range"),
        "Latitude": navigation.get("latitude"),
        "Longitude": navigation.get("longitude"),
        "Altitude (m)": navigation.get("altitude_m"),
        "Horizontal position accuracy (m)": navigation.get(
            "horizontal_position_accuracy_m"
        ),
        "Vertical position accuracy (m)": navigation.get(
            "vertical_position_accuracy_m"
        ),
        "Validity": navigation.get("validity"),
    }

    return info_table(data)


# ============================================================
# BATTERY / TELEMETRY / FAILSAFE
# ============================================================

def build_operational_analysis(analysis):

    content = ""

    battery = analysis.get("battery", {})

    if battery:
        content += "<h3>Battery</h3>"

        content += info_table({
            "Available": battery.get("available"),
            "Records": battery.get("record_count"),
            "Voltage (V)": battery.get("voltage_v"),
            "Current (A)": battery.get("current_a"),
            "Remaining": battery.get("remaining"),
            "Temperature (°C)": battery.get("temperature_c"),
            "Cell voltage delta (V)": battery.get(
                "cell_voltage_delta_v"
            ),
            "Connection": battery.get("connection"),
            "Faults": battery.get("faults"),
            "Time range": battery.get("time_range"),
        })

    telemetry = analysis.get("telemetry", {})

    if telemetry:
        content += "<h3>Telemetry</h3>"

        content += info_table({
            "Available": telemetry.get("available"),
            "Records": telemetry.get("record_count"),
            "Average TX rate": telemetry.get("tx_rate_avg"),
            "Average RX rate": telemetry.get("rx_rate_avg"),
            "RX message lost count": telemetry.get(
                "rx_message_lost_count"
            ),
            "RX parse errors": telemetry.get(
                "rx_parse_errors"
            ),
            "RX packet drop count": telemetry.get(
                "rx_packet_drop_count"
            ),
            "RX message lost rate": telemetry.get(
                "rx_message_lost_rate"
            ),
            "Protocol": telemetry.get("protocol"),
            "Time range": telemetry.get("time_range"),
        })

    failsafe = analysis.get("failsafe", {})

    if failsafe:
        content += "<h3>Failsafe</h3>"

        content += info_table({
            "Available": failsafe.get("available"),
            "Records": failsafe.get("record_count"),
            "Flags": failsafe.get("flags"),
            "Battery warning values": failsafe.get(
                "battery_warning_values"
            ),
            "Time range": failsafe.get("time_range"),
        })

    return content


# ============================================================
# COMMANDS
# ============================================================

def build_commands(analysis):

    commands = analysis.get("commands", {})

    if not commands:
        return "<p>No command analysis available.</p>"

    summary = info_table({
        "Commands": commands.get("command_count"),
        "Acknowledgements": commands.get(
            "acknowledgement_count"
        ),
        "Command IDs with ACK": commands.get(
            "command_ids_with_ack"
        ),
        "Command IDs without ACK": commands.get(
            "command_ids_without_ack"
        ),
        "ACK IDs without command": commands.get(
            "ack_ids_without_command"
        ),
    })

    tables = summary

    for title, key in [
        ("Command ID Counts", "command_id_counts"),
        (
            "Acknowledgement ID Counts",
            "acknowledgement_id_counts"
        ),
    ]:

        values = commands.get(key, {})

        if values:
            tables += f"<h3>{esc(title)}</h3>"
            tables += info_table(values)

    return tables


# ============================================================
# STATES
# ============================================================

def build_states(analysis):

    states = analysis.get("states", {})

    if not states:
        return "<p>No state analysis available.</p>"

    return info_table({
        "Available": states.get("available"),
        "State records": states.get("state_count"),
        "Flight modes": states.get("flight_modes"),
        "Armed states": states.get("armed_states"),
        "Failsafe states": states.get("failsafe_states"),
        "GCS connection states": states.get(
            "gcs_connection_states"
        ),
        "Time range": states.get("time_range"),
    })


# ============================================================
# EVENTS
# ============================================================

def build_events(analysis):

    events = analysis.get("events", {})

    if not events:
        return "<p>No native event analysis available.</p>"

    event_types = events.get(
        "event_types",
        {},
    )

    content = info_table({
        "Native event count": events.get(
            "event_count"
        ),
        "Event types": event_types,
    })

    # Preserve platform-specific native event information
    # only when the normalized analysis provides it.
    native_detail_fields = {}

    for key, value in events.items():

        if key in {
            "event_count",
            "event_types",
            "severity_counts",
        }:
            continue

        if value:
            native_detail_fields[key] = value

    if native_detail_fields:

        content += "<h3>Platform-Native Event Details</h3>"

        content += info_table(
            native_detail_fields
        )

    content += """
    <div class="notice">

        <strong>Native event handling:</strong>

        Numeric or platform-native event identifiers and
        associated native fields are preserved as evidence.
        Human-readable meanings and generic security severity
        labels are not inferred unless a defensible mapping
        is available.

    </div>
    """

    return content


# ============================================================
# SECURITY INDICATORS
# ============================================================

def _format_timestamp(value):
    """Format a normalized forensic timestamp in seconds."""
    if value is None:
        return "N/A"

    try:
        return f"{float(value):.3f} s"
    except (TypeError, ValueError):
        return str(value)


def _format_duration(start, end):
    """Calculate duration from normalized start/end timestamps."""
    if start is None or end is None:
        return "N/A"

    try:
        duration = float(end) - float(start)
    except (TypeError, ValueError):
        return "N/A"

    if duration < 0:
        return "N/A"

    return f"{duration:.3f} s"


# ============================================================
# SECURITY INDICATORS
# ============================================================

def build_security_indicators(data):

    if not isinstance(data, dict):
        return "<p>No security indicators available.</p>"

    all_indicators = []

    for category, values in data.items():

        if category == "summary":
            continue

        if isinstance(values, list):

            for indicator in values:

                if isinstance(indicator, dict):

                    item = dict(indicator)
                    item["_category"] = category
                    all_indicators.append(item)

    summary = data.get("summary", {})

    content = ""

    if summary:
        content += "<h3>Security Analysis Summary</h3>"
        content += info_table(summary)

    if not all_indicators:
        return content + "<p>No security indicators recorded.</p>"

    rows = []

    for indicator in all_indicators:

        severity = indicator.get("severity", "INFO")
        severity_class = str(severity).lower()

        start_time = indicator.get(
            "timestamp_seconds",
            indicator.get("timestamp")
        )

        end_time = indicator.get(
            "end_timestamp_seconds",
            indicator.get("end_timestamp")
        )

        duration = _format_duration(start_time, end_time)

        rows.append(
            "<tr>"
            f"<td>{esc(indicator.get('_category', ''))}</td>"
            f"<td>{status_badge(severity, severity_class)}</td>"
            f"<td>{esc(indicator.get('indicator_type', indicator.get('type', '')))}</td>"
            f"<td>{esc(indicator.get('description', indicator.get('title', '')))}</td>"
            f"<td>{esc(indicator.get('confidence', ''))}</td>"
            f"<td>{esc(_format_timestamp(start_time))}</td>"
            f"<td>{esc(_format_timestamp(end_time))}</td>"
            f"<td>{esc(duration)}</td>"
            "</tr>"
        )

    content += f"""
    <h3>Indicators</h3>

    <table class="data-table">

        <thead>
            <tr>
                <th>Category</th>
                <th>Severity</th>
                <th>Indicator</th>
                <th>Description</th>
                <th>Confidence</th>
                <th>Start Time</th>
                <th>End Time</th>
                <th>Duration</th>
            </tr>
        </thead>

        <tbody>
            {"".join(rows)}
        </tbody>

    </table>
    """

    return content


# ============================================================
# FINDINGS
# ============================================================

def build_findings(findings):

    if not findings:
        return "<p>No forensic findings recorded.</p>"

    rows = []

    for finding in findings:

        severity = finding.get("severity", "INFO")
        severity_class = str(severity).lower()

        start_time = finding.get(
            "timestamp",
            finding.get("timestamp_seconds")
        )

        end_time = finding.get(
            "end_timestamp",
            finding.get("end_timestamp_seconds")
        )

        duration = _format_duration(start_time, end_time)

        rows.append(
            "<tr>"
            f"<td>{esc(finding.get('finding_id', ''))}</td>"
            f"<td>{esc(finding.get('category', ''))}</td>"
            f"<td>{status_badge(severity, severity_class)}</td>"
            f"<td><strong>{esc(finding.get('title', ''))}</strong><br>"
            f"{esc(finding.get('description', ''))}</td>"
            f"<td>{esc(_format_timestamp(start_time))}</td>"
            f"<td>{esc(_format_timestamp(end_time))}</td>"
            f"<td>{esc(duration)}</td>"
            f"<td>{esc(finding.get('confidence', ''))}</td>"
            "</tr>"
        )

    high_count = sum(
        1 for f in findings
        if str(f.get("severity", "")).upper() == "HIGH"
    )

    medium_count = sum(
        1 for f in findings
        if str(f.get("severity", "")).upper() == "MEDIUM"
    )

    info_count = sum(
        1 for f in findings
        if str(f.get("severity", "")).upper() == "INFO"
    )

    return f"""
    <div class="summary-cards">

        <div class="card">
            <div class="card-number">
                {len(findings)}
            </div>
            <div class="card-label">
                Forensic Findings
            </div>
        </div>

        <div class="card">
            <div class="card-number">
                {high_count}
            </div>
            <div class="card-label">
                High
            </div>
        </div>

        <div class="card">
            <div class="card-number">
                {medium_count}
            </div>
            <div class="card-label">
                Medium
            </div>
        </div>

        <div class="card">
            <div class="card-number">
                {info_count}
            </div>
            <div class="card-label">
                Informational
            </div>
        </div>

    </div>

    <table class="data-table">

        <thead>
            <tr>
                <th>Finding ID</th>
                <th>Category</th>
                <th>Severity</th>
                <th>Finding</th>
                <th>Start Time</th>
                <th>End Time</th>
                <th>Duration</th>
                <th>Confidence</th>
            </tr>
        </thead>

        <tbody>
            {"".join(rows)}
        </tbody>

    </table>
    """



def build_timeline(timeline):

    if not timeline:
        return "<p>No reconstructed timeline available.</p>"

    events = timeline.get("events", [])

    if not events:
        return "<p>No timeline events available.</p>"

    rows = []

    for event in events:

        details = event.get(
            "details",
            event.get("data", {})
        )

        rows.append(
            "<tr>"
            f"<td>{esc(fmt(event.get('timestamp_seconds', event.get('timestamp'))))}</td>"
            f"<td>{esc(event.get('event_type', ''))}</td>"
            f"<td>{render_value(details)}</td>"
            "</tr>"
        )

    return f"""
    <p>
        Total reconstructed timeline events:
        <strong>{len(events)}</strong>
    </p>

    <p>
        Correlations:
        <strong>{esc(timeline.get('correlation_count', 0))}</strong>
    </p>

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

    <div class="notice">
        {esc(timeline.get("forensic_note", ""))}
    </div>
    """


# ============================================================
# HTML GENERATION
# ============================================================

def generate_report(input_path, output_path):

    data = load_json(input_path)

    evidence = data.get("evidence", {})
    integrity = data.get("integrity", {})
    record_counts = data.get("record_counts", {})
    analysis = data.get("analysis", {})
    security = data.get("security_indicators", {})
    findings = data.get("findings", [])
    provenance = data.get("provenance", {})

    # ------------------------------------------------------------
    # NORMALIZED VISUALIZATIONS
    # ------------------------------------------------------------
    #
    # The analysis JSON contains normalized results, while the
    # visualization layer operates on NormalizedEvidence objects.
    # Reparse the original evidence through the platform registry
    # so the visualization layer remains platform-independent.
    #
    # Visualization generation is intentionally non-fatal:
    # inability to regenerate a plot must not prevent the forensic
    # report itself from being produced.
    # ------------------------------------------------------------

    visualization_result = {
        "generated": {},
        "unavailable": {},
        "output_dir": None,
    }

    normalized_evidence = None

    try:
        raw_source = evidence.get("source_file")

        candidate_paths = []

        if raw_source:
            raw_path = Path(raw_source).expanduser()

            if raw_path.is_absolute():
                candidate_paths.append(raw_path)
            else:
                candidate_paths.extend(
                    [
                        Path.cwd() / raw_path,
                        Path(__file__).resolve().parent.parent / raw_path,
                    ]
                )

        # If the stored source path is incomplete, try to resolve it
        # using the case/evidence identifiers.
        if not any(candidate.is_file() for candidate in candidate_paths):
            case_root = (
                Path(__file__).resolve().parent.parent
                / "repository"
                / "cases"
                / case_id
            )

            candidate_paths.extend(
                [
                    case_root / "raw" / source_name,
                    case_root / source_name,
                ]
            )

        source_path = next(
            (
                candidate.resolve()
                for candidate in candidate_paths
                if candidate.is_file()
            ),
            None,
        )

        if source_path is None:
            visualization_result["unavailable"][
                "all_visualizations"
            ] = (
                "Original evidence source could not be resolved "
                "from the normalized report."
            )
        else:
            try:
                registry = ParserRegistry()
                parser = registry.get_parser(source_path)
                normalized_evidence = parser.parse()

                visualization_dir = (
                    Path(output_path).resolve().parent
                    / f"{Path(output_path).stem}_plots"
                )

                # Flatten all normalized security indicators.
                #
                # The JSON structure contains a "summary" object
                # plus one or more indicator lists.
                all_indicators = []

                if isinstance(security, dict):
                    for key, value in security.items():
                        if key == "summary":
                            continue

                        if isinstance(value, list):
                            all_indicators.extend(value)

                visualization_result = generate_visualizations(
                    normalized_evidence,
                    visualization_dir,
                    security_indicators=all_indicators,
                )

            except Exception as exc:
                visualization_result["unavailable"][
                    "all_visualizations"
                ] = (
                    "Visualization generation failed: "
                    f"{type(exc).__name__}: {exc}"
                )

    except Exception as exc:
        visualization_result["unavailable"][
            "all_visualizations"
        ] = (
            "Visualization preparation failed: "
            f"{type(exc).__name__}: {exc}"
        )

    visualization_titles = {
        "trajectory": "Flight Trajectory",
        "altitude": "Altitude vs Time",
        "speed": "Speed vs Time",
        "battery_voltage": "Battery Voltage vs Time",
        "battery_current": "Battery Current vs Time",
        "battery_remaining": "Battery Remaining vs Time",
        "battery_temperature": "Battery Temperature vs Time",
        "battery_cell_delta": "Maximum Cell-Voltage Delta vs Time",
        "telemetry_rates": "Telemetry Rates vs Time",
        "telemetry_loss": "Telemetry Loss / Packet-Loss Indicators",
        "failsafe": "Failsafe Timeline",
        "state": "Vehicle State Timeline",
        "command_ack": "Command / ACK Timeline",
        "events": "Native Event Timeline",
        "security_indicators": "Security Indicator Timeline",
    }

    visualization_descriptions = {
        "trajectory": (
            "Horizontal flight path reconstructed from normalized "
            "navigation records."
        ),
        "altitude": (
            "Altitude observations plotted against the normalized "
            "evidence timeline."
        ),
        "speed": (
            "Recorded GPS speed observations plotted against time."
        ),
        "battery_voltage": (
            "Battery voltage observations over the evidence timeline."
        ),
        "battery_current": (
            "Battery current observations over the evidence timeline."
        ),
        "battery_remaining": (
            "Reported battery remaining values over time."
        ),
        "battery_temperature": (
            "Recorded battery temperature observations over time."
        ),
        "battery_cell_delta": (
            "Maximum observed cell-voltage difference over time."
        ),
        "telemetry_rates": (
            "Normalized telemetry transmit and receive rate observations."
        ),
        "telemetry_loss": (
            "Normalized telemetry loss, drop, and error observations."
        ),
        "failsafe": (
            "Normalized failsafe conditions reconstructed from the evidence."
        ),
        "state": (
            "Normalized armed, flight-mode, failsafe, and connection "
            "state transitions."
        ),
        "command_ack": (
            "Vehicle command and command-acknowledgement observations "
            "plotted on the normalized timeline."
        ),
        "events": (
            "Platform-native event observations preserved from the "
            "source evidence."
        ),
        "security_indicators": (
            "Security indicators generated by the normalized analysis "
            "layer. These are investigative observations, not proof "
            "of malicious activity."
        ),
    }

    visualization_html = build_visualizations(
        visualization_result,
        titles=visualization_titles,
    )


    source_file = Path(
        evidence.get(
            "source_file",
            input_path
        )
    )

    case_id = evidence.get("case_id")

    if not case_id:
        parts = source_file.parts

        if "cases" in parts:
            index = parts.index("cases")

            if index + 1 < len(parts):
                case_id = parts[index + 1]

    case_id = case_id or "UNKNOWN"

    evidence_id = evidence.get(
        "evidence_id"
    ) or f"{case_id}/raw"

    source_name = source_file.name

    generated_time = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    metadata = {
        "Case ID": case_id,
        "Evidence ID": evidence_id,
        "Platform": evidence.get("platform"),
        "Format": evidence.get("format"),
        "Source File": source_name,
        "Firmware": evidence.get("firmware"),
        "Vehicle Type": evidence.get("vehicle_type"),
        "Start Time (s)": evidence.get("start_time"),
        "End Time (s)": evidence.get("end_time"),
        "Duration (s)": evidence.get("duration"),
    }

    integrity_table = {
        "Hash Algorithm": integrity.get("hash_algorithm"),
        "Evidence SHA-256": integrity.get("evidence_hash"),
    }

    provenance_table = {
        "Platform": provenance.get("platform"),
        "Format": provenance.get("format"),
        "Normalized GPS Records": provenance.get(
            "normalized_records",
            {}
        ).get("gps"),
        "Normalized Commands": provenance.get(
            "normalized_records",
            {}
        ).get("commands"),
        "Normalized ACKs": provenance.get(
            "normalized_records",
            {}
        ).get("command_acks"),
        "Normalized States": provenance.get(
            "normalized_records",
            {}
        ).get("states"),
        "Normalized Parameters": provenance.get(
            "normalized_records",
            {}
        ).get("parameters"),
        "Normalized Events": provenance.get(
            "normalized_records",
            {}
        ).get("events"),
    }

    conclusion = """
    <div class="notice">

        <strong>Evidence interpretation:</strong>

        <p>
            The findings in this report represent observations
            reconstructed from the analyzed normalized evidence
            and the underlying source evidence.
        </p>

        <p>
            Security indicators identify conditions that may
            warrant further investigation. They do not, by
            themselves, establish malicious intent, unauthorized
            access, or the occurrence of a cyberattack.
        </p>

        <p>
            Command/ACK relationships, state transitions,
            telemetry conditions, failsafe records, navigation
            observations, and platform-native events are reported as
            recorded or analytically reconstructed evidence.
        </p>

        <p>
            Temporal proximity between events is not treated as
            proof of causality.
        </p>

    </div>
    """

    html_document = f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>
Drone Forensic Examination Report - {esc(case_id)}
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



.plot-card {{
    margin: 24px 0;
    padding: 18px;
    border: 1px solid #d9dee7;
    border-radius: 10px;
    background: #ffffff;
}}

.plot-card h3 {{
    margin-top: 0;
    margin-bottom: 10px;
}}

.plot-description {{
    color: #5f6b7a;
    margin-bottom: 14px;
}}

.forensic-plot {{
    display: block;
    width: 100%;
    max-width: 1200px;
    height: auto;
    margin: 0 auto;
    border-radius: 6px;
}}

.plot-card img {{
    background: #ffffff;
}}

</style>

</head>

<body>

<div class="container">

<header>

<h1>
Drone Forensic Examination Report
</h1>

<p>
<strong>Case:</strong>
{esc(case_id)}
</p>

<p>
<strong>Evidence:</strong>
{esc(evidence_id)}
</p>

<p>
<strong>Source:</strong>
{esc(source_name)}
</p>

<p>
<strong>Platform:</strong>
{esc(evidence.get("platform", "N/A"))}
</p>

<p>
<strong>Generated:</strong>
{esc(generated_time)}
</p>

</header>


{section(
    "1. Case Information",
    info_table(metadata)
)}


{section(
    "2. Evidence Integrity",
    info_table(integrity_table)
)}


{section(
    "3. Evidence Provenance",
    info_table(provenance_table)
)}


{section(
    "4. Evidence Extraction Summary",
    build_record_summary(record_counts)
    + build_analysis_summary(analysis)
)}


{section(
    "5. Forensic Visualizations",
    visualization_html
)}


{section(
    "6. Navigation Analysis",
    build_navigation(analysis)
)}


{section(
    "7. Battery / Telemetry / Failsafe Analysis",
    build_operational_analysis(analysis)
)}


{section(
    "8. Command and ACK Forensics",
    build_commands(analysis)
)}


{section(
    "9. State Reconstruction",
    build_states(analysis)
)}


{section(
    "10. Native Events",
    build_events(analysis)
)}


{section(
    "11. Security Indicators",
    build_security_indicators(security)
)}


{section(
    "12. Forensic Findings",
    build_findings(findings)
)}


{section(
    "13. Forensic Timeline",
    build_timeline(
        analysis.get("timeline", {})
    )
)}


{section(
    "14. Evidence-Based Interpretation",
    conclusion
)}


{section(
    "15. Analyst Notes and Limitations",
    """
    <ul>

        <li>
            Findings are based on the available normalized
            source evidence.
        </li>

        <li>
            Absence of a recorded indicator does not prove
            absence of an underlying event.
        </li>

        <li>
            Platform-native event identifiers are preserved without
            assigning unsupported semantic meanings.
        </li>

        <li>
            GCS connection state changes are reported as
            communication-state observations and are not
            automatically classified as cyberattacks.
        </li>

        <li>
            Command/ACK matching uses recorded command
            identifiers and configured matching logic.
        </li>

        <li>
            Temporal proximity between evidence records is not
            treated as proof of causality.
        </li>

        <li>
            Security findings are analytical outputs and should
            be interpreted together with their underlying
            evidence references.
        </li>

    </ul>
    """
)}


<footer>

Drone Forensics Toolkit
<br>
Normalized multi-platform forensic report

</footer>

</div>

</body>

</html>
"""

    output_path = Path(output_path)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path.write_text(
        html_document,
        encoding="utf-8"
    )

    print("=" * 70)
    print("NORMALIZED DRONE FORENSIC REPORT")
    print("=" * 70)
    print()
    print(f"Case:       {case_id}")
    print(f"Evidence:   {evidence_id}")
    print(f"Platform:   {evidence.get('platform')}")
    print(f"Format:     {evidence.get('format')}")
    print()
    print("Record counts:")
    for key, value in record_counts.items():
        print(f"  {key:<18}: {value}")
    print()
    print(f"Findings:   {len(findings)}")
    print()
    print("Report generated:")
    print(output_path)
    print()
    print(f"Report size: {output_path.stat().st_size:,} bytes")
    print()
    print("STATUS: SUCCESS")
    print("=" * 70)


# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Generate styled normalized drone forensic HTML report."
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Normalized analysis JSON file"
    )

    parser.add_argument(
        "--output",
        default="reporting/normalized_forensic_report.html",
        help="Output HTML report"
    )

    args = parser.parse_args()

    generate_report(
        args.input,
        args.output
    )


if __name__ == "__main__":
    main()
