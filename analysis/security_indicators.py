import json
import os
import statistics
from pyulog import ULog


# ============================================================
# CONFIGURATION
# ============================================================

CASE_ID = "CASE-001"
EVIDENCE_ID = "EVD-20260919-175126"

BASE_DIR = (
    f"repository/cases/{CASE_ID}/{EVIDENCE_ID}"
)

EVIDENCE_FILE = (
    f"{BASE_DIR}/evidence/17_02_27.ulg"
)

ANALYSIS_DIR = f"{BASE_DIR}/analysis"

OUTPUT_FILE = (
    f"{ANALYSIS_DIR}/security_indicators.json"
)


# ============================================================
# HELPERS
# ============================================================

def scalar(value):
    if hasattr(value, "item"):
        return value.item()
    return value


def rows_from_dataset(dataset):

    data = dataset.data

    if "timestamp" not in data:
        return []

    count = len(data["timestamp"])

    rows = []

    for i in range(count):

        row = {}

        for field in data:
            row[field] = scalar(data[field][i])

        rows.append(row)

    return rows


def timestamp_seconds(timestamp_us):
    return timestamp_us / 1_000_000.0


# ============================================================
# LOAD ULOG
# ============================================================

if not os.path.exists(EVIDENCE_FILE):
    raise FileNotFoundError(EVIDENCE_FILE)

ulog = ULog(EVIDENCE_FILE)


# ============================================================
# FIND DATASETS SAFELY
# ============================================================

dataset_names = {
    dataset.name
    for dataset in ulog.data_list
}


def get_rows(name):

    if name not in dataset_names:
        return []

    return rows_from_dataset(
        ulog.get_dataset(name)
    )


gps = get_rows("vehicle_gps_position")
vehicle_status = get_rows("vehicle_status")
land_detected = get_rows("vehicle_land_detected")
commands = get_rows("vehicle_command")
acks = get_rows("vehicle_command_ack")


# ============================================================
# INDICATORS
# ============================================================

indicators = []


def add_indicator(
    category,
    indicator_type,
    severity,
    timestamp_seconds_value,
    description,
    evidence,
    confidence="OBSERVED"
):

    indicators.append(
        {
            "category": category,
            "indicator_type": indicator_type,
            "severity": severity,
            "timestamp_seconds":
                timestamp_seconds_value,
            "confidence": confidence,
            "description": description,
            "evidence": evidence,
        }
    )


# ============================================================
# 1. GPS SPOOFING / JAMMING STATE
# ============================================================

gps_spoofing_samples = [
    row for row in gps
    if int(row.get("spoofing_state", 0)) != 0
]

gps_jamming_samples = [
    row for row in gps
    if (
        int(row.get("jamming_state", 0)) != 0
        or int(row.get("jamming_indicator", 0)) != 0
    )
]


if gps_spoofing_samples:

    for row in gps_spoofing_samples[:20]:

        add_indicator(
            category="NAVIGATION",
            indicator_type="GPS_SPOOFING_STATE_ASSERTED",
            severity="HIGH",
            timestamp_seconds_value=
                timestamp_seconds(row["timestamp"]),
            description=(
                "PX4 GPS telemetry recorded a "
                "non-zero spoofing state."
            ),
            evidence={
                "spoofing_state":
                    int(row["spoofing_state"]),
                "latitude_deg":
                    row.get("latitude_deg"),
                "longitude_deg":
                    row.get("longitude_deg"),
            },
            confidence="OBSERVED"
        )

else:

    add_indicator(
        category="NAVIGATION",
        indicator_type="GPS_SPOOFING_STATE_NOT_ASSERTED",
        severity="INFO",
        timestamp_seconds_value=None,
        description=(
            "No analyzed GPS sample asserted a "
            "non-zero PX4 spoofing state."
        ),
        evidence={
            "gps_samples":
                len(gps),
            "observed_spoofing_states":
                sorted(
                    {
                        int(row.get("spoofing_state", 0))
                        for row in gps
                    }
                ),
        },
        confidence="OBSERVED"
    )


if gps_jamming_samples:

    for row in gps_jamming_samples[:20]:

        add_indicator(
            category="NAVIGATION",
            indicator_type="GPS_JAMMING_STATE_ASSERTED",
            severity="HIGH",
            timestamp_seconds_value=
                timestamp_seconds(row["timestamp"]),
            description=(
                "PX4 GPS telemetry recorded a "
                "non-zero jamming state or indicator."
            ),
            evidence={
                "jamming_state":
                    int(row.get("jamming_state", 0)),
                "jamming_indicator":
                    int(row.get("jamming_indicator", 0)),
            },
            confidence="OBSERVED"
        )

else:

    add_indicator(
        category="NAVIGATION",
        indicator_type="GPS_JAMMING_STATE_NOT_ASSERTED",
        severity="INFO",
        timestamp_seconds_value=None,
        description=(
            "No analyzed GPS sample asserted a "
            "non-zero PX4 jamming state or indicator."
        ),
        evidence={
            "gps_samples":
                len(gps),
        },
        confidence="OBSERVED"
    )


# ============================================================
# 2. GPS FIX CHANGES
# ============================================================

if gps:

    fix_types = [
        int(row["fix_type"])
        for row in gps
        if row.get("fix_type") is not None
    ]

    unique_fix_types = sorted(
        set(fix_types)
    )

    if len(unique_fix_types) > 1:

        add_indicator(
            category="NAVIGATION",
            indicator_type="GPS_FIX_TYPE_CHANGE",
            severity="MEDIUM",
            timestamp_seconds_value=None,
            description=(
                "More than one GPS fix type was "
                "observed in the analyzed telemetry."
            ),
            evidence={
                "observed_fix_types":
                    unique_fix_types,
            },
            confidence="OBSERVED"
        )


# ============================================================
# 3. SATELLITE COUNT CHANGES
# ============================================================

if gps:

    satellites = [
        int(row["satellites_used"])
        for row in gps
        if row.get("satellites_used") is not None
    ]

    unique_satellites = sorted(
        set(satellites)
    )

    if len(unique_satellites) > 1:

        add_indicator(
            category="NAVIGATION",
            indicator_type="GPS_SATELLITE_COUNT_CHANGE",
            severity="LOW",
            timestamp_seconds_value=None,
            description=(
                "The number of satellites used by "
                "the recorded GPS solution changed."
            ),
            evidence={
                "min":
                    min(satellites),
                "max":
                    max(satellites),
                "unique_values":
                    unique_satellites,
            },
            confidence="OBSERVED"
        )


# ============================================================
# 4. GCS CONNECTION LOSS
# ============================================================

gcs_events = []

if vehicle_status:

    previous = None

    for row in vehicle_status:

        current = int(
            row["gcs_connection_lost"]
        )

        if previous is None:

            previous = current
            continue

        if current != previous:

            t = timestamp_seconds(
                row["timestamp"]
            )

            gcs_events.append(
                {
                    "timestamp_seconds": t,
                    "previous_state": previous,
                    "new_state": current,
                }
            )

            if current == 1:

                add_indicator(
                    category="COMMAND_AND_CONTROL",
                    indicator_type="GCS_CONNECTION_LOST",
                    severity="MEDIUM",
                    timestamp_seconds_value=t,
                    description=(
                        "PX4 recorded a transition "
                        "to GCS connection lost."
                    ),
                    evidence={
                        "previous_state": previous,
                        "new_state": current,
                    },
                    confidence="OBSERVED"
                )

            else:

                add_indicator(
                    category="COMMAND_AND_CONTROL",
                    indicator_type="GCS_CONNECTION_RESTORED",
                    severity="INFO",
                    timestamp_seconds_value=t,
                    description=(
                        "PX4 recorded restoration of "
                        "the GCS connection state."
                    ),
                    evidence={
                        "previous_state": previous,
                        "new_state": current,
                    },
                    confidence="OBSERVED"
                )

            previous = current


# ============================================================
# 5. FAILSAFE STATE
# ============================================================

failsafe_states = sorted(
    {
        int(row["failsafe"])
        for row in vehicle_status
        if row.get("failsafe") is not None
    }
)


if any(state != 0 for state in failsafe_states):

    add_indicator(
        category="FLIGHT_CONTROL",
        indicator_type="FAILSAFE_STATE_OBSERVED",
        severity="HIGH",
        timestamp_seconds_value=None,
        description=(
            "At least one recorded vehicle status "
            "sample indicated a non-zero failsafe state."
        ),
        evidence={
            "observed_failsafe_states":
                failsafe_states,
        },
        confidence="OBSERVED"
    )

else:

    add_indicator(
        category="FLIGHT_CONTROL",
        indicator_type="NO_NONZERO_FAILSAFE_STATE_OBSERVED",
        severity="INFO",
        timestamp_seconds_value=None,
        description=(
            "No non-zero failsafe state was observed "
            "in the analyzed vehicle status samples."
        ),
        evidence={
            "observed_failsafe_states":
                failsafe_states,
        },
        confidence="OBSERVED"
    )


# ============================================================
# 6. EXTERNAL COMMANDS
# ============================================================

external_commands = [
    row for row in commands
    if int(row.get("from_external", 0)) == 1
]


if external_commands:

    add_indicator(
        category="COMMAND_AND_CONTROL",
        indicator_type="EXTERNAL_COMMANDS_OBSERVED",
        severity="INFO",
        timestamp_seconds_value=None,
        description=(
            "Vehicle command records marked "
            "from_external were observed."
        ),
        evidence={
            "count":
                len(external_commands),
            "command_ids":
                sorted(
                    {
                        int(row["command"])
                        for row in external_commands
                    }
                ),
        },
        confidence="OBSERVED"
    )


# ============================================================
# 7. COMMAND/ACK ID MISMATCH
# ============================================================

command_ids = {
    int(row["command"])
    for row in commands
}

ack_ids = {
    int(row["command"])
    for row in acks
}


acks_without_command_id = sorted(
    ack_ids - command_ids
)


commands_without_ack_id = sorted(
    command_ids - ack_ids
)


if acks_without_command_id:

    add_indicator(
        category="COMMAND_AND_CONTROL",
        indicator_type="ACK_COMMAND_ID_WITHOUT_COMMAND",
        severity="LOW",
        timestamp_seconds_value=None,
        description=(
            "ACK command IDs were observed for which "
            "no vehicle_command record with the same "
            "command ID exists in the analyzed ULog."
        ),
        evidence={
            "ack_command_ids":
                acks_without_command_id,
        },
        confidence="OBSERVED"
    )


if commands_without_ack_id:

    add_indicator(
        category="COMMAND_AND_CONTROL",
        indicator_type="COMMAND_ID_WITHOUT_ACK",
        severity="LOW",
        timestamp_seconds_value=None,
        description=(
            "Vehicle command IDs were observed for which "
            "no vehicle_command_ack record with the same "
            "command ID exists in the analyzed ULog."
        ),
        evidence={
            "command_ids":
                commands_without_ack_id,
        },
        confidence="OBSERVED"
    )


# ============================================================
# 8. LOG INTEGRITY / DATA QUALITY
# ============================================================

if hasattr(ulog, "dropouts"):

    dropout_count = len(ulog.dropouts)

else:

    dropout_count = 0


if dropout_count > 0:

    add_indicator(
        category="EVIDENCE_QUALITY",
        indicator_type="LOG_DROPOUTS",
        severity="MEDIUM",
        timestamp_seconds_value=None,
        description=(
            "The ULog contains recorded logging "
            "dropout intervals."
        ),
        evidence={
            "dropout_count":
                dropout_count,
        },
        confidence="OBSERVED"
    )

else:

    add_indicator(
        category="EVIDENCE_QUALITY",
        indicator_type="NO_LOG_DROPOUTS_REPORTED",
        severity="INFO",
        timestamp_seconds_value=None,
        description=(
            "The ULog reports no logging dropouts."
        ),
        evidence={
            "dropout_count":
                dropout_count,
        },
        confidence="OBSERVED"
    )


# ============================================================
# SUMMARY
# ============================================================

severity_counts = {}

for indicator in indicators:

    severity = indicator["severity"]

    severity_counts[severity] = (
        severity_counts.get(severity, 0) + 1
    )


category_counts = {}

for indicator in indicators:

    category = indicator["category"]

    category_counts[category] = (
        category_counts.get(category, 0) + 1
    )


result = {

    "case_id":
        CASE_ID,

    "evidence_id":
        EVIDENCE_ID,

    "source":
        EVIDENCE_FILE,

    "indicator_count":
        len(indicators),

    "severity_counts":
        severity_counts,

    "category_counts":
        category_counts,

    "indicators":
        indicators,
}


# ============================================================
# WRITE OUTPUT
# ============================================================

os.makedirs(
    ANALYSIS_DIR,
    exist_ok=True
)

with open(
    OUTPUT_FILE,
    "w"
) as f:

    json.dump(
        result,
        f,
        indent=4
    )


# ============================================================
# TERMINAL OUTPUT
# ============================================================

print("=" * 70)
print("PX4 SECURITY INDICATOR ANALYSIS")
print("=" * 70)

print()
print(f"GPS samples:       {len(gps)}")
print(f"Vehicle states:    {len(vehicle_status)}")
print(f"Commands:          {len(commands)}")
print(f"ACKs:              {len(acks)}")

print()
print("Indicators:", len(indicators))

print()
print("Severity counts:")

for severity, count in sorted(
    severity_counts.items()
):

    print(
        f"  {severity}: {count}"
    )

print()
print("Category counts:")

for category, count in sorted(
    category_counts.items()
):

    print(
        f"  {category}: {count}"
    )

print()
print("Output:")
print(OUTPUT_FILE)
