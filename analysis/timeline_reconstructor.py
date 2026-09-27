import json
from pathlib import Path
from pyulog import ULog


# ============================================================
# CONFIGURATION
# ============================================================

CASE_ID = "CASE-001"
EVIDENCE_ID = "EVD-20260919-175126"

BASE_DIR = Path("repository/cases") / CASE_ID / EVIDENCE_ID

EVIDENCE_FILE = (
    BASE_DIR
    / "evidence"
    / "17_02_27.ulg"
)

OUTPUT_FILE = (
    BASE_DIR
    / "analysis"
    / "forensic_timeline.json"
)


# ============================================================
# DATASET HELPERS
# ============================================================

def get_dataset(ulog, name):

    try:
        datasets = ulog.get_dataset(name)

        if datasets is None:
            return None

        return datasets

    except Exception:
        return None


def get_data(dataset):

    if dataset is None:
        return None

    return dataset.data


def get_value(data, field, index):

    if data is None:
        return None

    if field not in data:
        return None

    try:
        value = data[field][index]

        # Convert NumPy scalar types to normal Python types
        if hasattr(value, "item"):
            return value.item()

        return value

    except (IndexError, KeyError):
        return None

# ============================================================
# TIMESTAMP CONVERSION
# ============================================================

def timestamp_seconds(timestamp_us):

    if timestamp_us is None:
        return None

    return timestamp_us / 1_000_000.0


# ============================================================
# EVENT CREATION
# ============================================================

def create_event(
    timestamp_us,
    event_type,
    source_dataset,
    details=None,
    severity="INFO"
):

    return {
        "timestamp_us": int(timestamp_us),
        "timestamp_seconds": timestamp_seconds(timestamp_us),
        "event_type": event_type,
        "source_dataset": source_dataset,
        "severity": severity,
        "details": details or {}
    }


# ============================================================
# VEHICLE STATUS EVENTS
# ============================================================

def extract_vehicle_status_events(ulog):

    events = []

    dataset = get_dataset(
        ulog,
        "vehicle_status"
    )

    if dataset is None:
        return events

    data = get_data(dataset)

    if data is None:
        return events

    previous_arming_state = None
    previous_nav_state = None
    previous_failsafe = None
    previous_gcs_lost = None

    for i in range(len(data["timestamp"])):

        timestamp = get_value(
            data,
            "timestamp",
            i
        )

        if timestamp is None:
            continue

        # ----------------------------------------------------
        # Arming state
        # ----------------------------------------------------

        arming_state = get_value(
            data,
            "arming_state",
            i
        )

        if (
            previous_arming_state is not None
            and arming_state != previous_arming_state
        ):

            events.append(
                create_event(
                    timestamp,
                    "ARMING_STATE_CHANGE",
                    "vehicle_status",
                    {
                        "previous": previous_arming_state,
                        "current": arming_state
                    }
                )
            )

        previous_arming_state = arming_state

        # ----------------------------------------------------
        # Navigation state
        # ----------------------------------------------------

        nav_state = get_value(
            data,
            "nav_state",
            i
        )

        if (
            previous_nav_state is not None
            and nav_state != previous_nav_state
        ):

            events.append(
                create_event(
                    timestamp,
                    "NAVIGATION_STATE_CHANGE",
                    "vehicle_status",
                    {
                        "previous": previous_nav_state,
                        "current": nav_state
                    }
                )
            )

        previous_nav_state = nav_state

        # ----------------------------------------------------
        # Failsafe
        # ----------------------------------------------------

        failsafe = get_value(
            data,
            "failsafe",
            i
        )

        if (
            previous_failsafe is not None
            and failsafe != previous_failsafe
        ):

            severity = (
                "WARNING"
                if failsafe
                else "INFO"
            )

            events.append(
                create_event(
                    timestamp,
                    "FAILSAFE_STATE_CHANGE",
                    "vehicle_status",
                    {
                        "previous": previous_failsafe,
                        "current": failsafe
                    },
                    severity
                )
            )

        previous_failsafe = failsafe

        # ----------------------------------------------------
        # GCS connection
        # ----------------------------------------------------

        gcs_lost = get_value(
            data,
            "gcs_connection_lost",
            i
        )

        if (
            previous_gcs_lost is not None
            and gcs_lost != previous_gcs_lost
        ):

            severity = (
                "WARNING"
                if gcs_lost
                else "INFO"
            )

            events.append(
                create_event(
                    timestamp,
                    "GCS_CONNECTION_STATE_CHANGE",
                    "vehicle_status",
                    {
                        "previous": previous_gcs_lost,
                        "current": gcs_lost
                    },
                    severity
                )
            )

        previous_gcs_lost = gcs_lost

    return events


# ============================================================
# VEHICLE LAND DETECTION
# ============================================================

def extract_land_events(ulog):

    events = []

    dataset = get_dataset(
        ulog,
        "vehicle_land_detected"
    )

    if dataset is None:
        return events

    data = get_data(dataset)

    if data is None:
        return events

    previous_landed = None

    for i in range(len(data["timestamp"])):

        timestamp = get_value(
            data,
            "timestamp",
            i
        )

        landed = get_value(
            data,
            "landed",
            i
        )

        if timestamp is None or landed is None:
            continue

        if (
            previous_landed is not None
            and landed != previous_landed
        ):

            event_type = (
                "LANDING_DETECTED"
                if landed
                else "TAKEOFF_DETECTED"
            )

            events.append(
                create_event(
                    timestamp,
                    event_type,
                    "vehicle_land_detected",
                    {
                        "previous": previous_landed,
                        "current": landed
                    }
                )
            )

        previous_landed = landed

    return events


# ============================================================
# COMMAND EVENTS
# ============================================================

def extract_command_events(ulog):

    events = []

    dataset = get_dataset(
        ulog,
        "vehicle_command"
    )

    if dataset is None:
        return events

    data = get_data(dataset)

    if data is None:
        return events

    for i in range(len(data["timestamp"])):

        timestamp = get_value(
            data,
            "timestamp",
            i
        )

        command = get_value(
            data,
            "command",
            i
        )

        if timestamp is None:
            continue

        events.append(
            create_event(
                timestamp,
                "VEHICLE_COMMAND",
                "vehicle_command",
                {
                    "command": command,
                    "param1": get_value(data, "param1", i),
                    "param2": get_value(data, "param2", i),
                    "param3": get_value(data, "param3", i),
                    "param4": get_value(data, "param4", i),
                    "param5": get_value(data, "param5", i),
                    "param6": get_value(data, "param6", i),
                    "param7": get_value(data, "param7", i)
                }
            )
        )

    return events


# ============================================================
# COMMAND ACK EVENTS
# ============================================================

def extract_command_ack_events(ulog):

    events = []

    dataset = get_dataset(
        ulog,
        "vehicle_command_ack"
    )

    if dataset is None:
        return events

    data = get_data(dataset)

    if data is None:
        return events

    for i in range(len(data["timestamp"])):

        timestamp = get_value(
            data,
            "timestamp",
            i
        )

        command = get_value(
            data,
            "command",
            i
        )

        result = get_value(
            data,
            "result",
            i
        )

        if timestamp is None:
            continue

        events.append(
            create_event(
                timestamp,
                "COMMAND_ACK",
                "vehicle_command_ack",
                {
                    "command": command,
                    "result": result
                }
            )
        )

    return events


# ============================================================
# GPS EVENTS
# ============================================================

def extract_gps_events(ulog):

    events = []

    dataset = get_dataset(
        ulog,
        "vehicle_gps_position"
    )

    if dataset is None:
        return events

    data = get_data(dataset)

    if data is None:
        return events

    previous_fix = None
    previous_satellites = None
    previous_spoofing = None
    previous_jamming = None

    for i in range(len(data["timestamp"])):

        timestamp = get_value(
            data,
            "timestamp",
            i
        )

        if timestamp is None:
            continue

        fix_type = get_value(
            data,
            "fix_type",
            i
        )

        satellites = get_value(
            data,
            "satellites_used",
            i
        )

        spoofing = get_value(
            data,
            "spoofing_state",
            i
        )

        jamming = get_value(
            data,
            "jamming_state",
            i
        )

        # ----------------------------------------------------
        # GPS fix transition
        # ----------------------------------------------------

        if (
            previous_fix is not None
            and fix_type != previous_fix
        ):

            events.append(
                create_event(
                    timestamp,
                    "GPS_FIX_STATE_CHANGE",
                    "vehicle_gps_position",
                    {
                        "previous": previous_fix,
                        "current": fix_type
                    },
                    "WARNING"
                )
            )

        # ----------------------------------------------------
        # Satellite transition
        # ----------------------------------------------------

        if (
            previous_satellites is not None
            and satellites != previous_satellites
        ):

            events.append(
                create_event(
                    timestamp,
                    "GPS_SATELLITE_COUNT_CHANGE",
                    "vehicle_gps_position",
                    {
                        "previous": previous_satellites,
                        "current": satellites
                    }
                )
            )

        # ----------------------------------------------------
        # Spoofing state
        # ----------------------------------------------------

        if (
            previous_spoofing is not None
            and spoofing != previous_spoofing
        ):

            events.append(
                create_event(
                    timestamp,
                    "GPS_SPOOFING_STATE_CHANGE",
                    "vehicle_gps_position",
                    {
                        "previous": previous_spoofing,
                        "current": spoofing
                    },
                    "WARNING"
                )
            )

        # ----------------------------------------------------
        # Jamming state
        # ----------------------------------------------------

        if (
            previous_jamming is not None
            and jamming != previous_jamming
        ):

            events.append(
                create_event(
                    timestamp,
                    "GPS_JAMMING_STATE_CHANGE",
                    "vehicle_gps_position",
                    {
                        "previous": previous_jamming,
                        "current": jamming
                    },
                    "WARNING"
                )
            )

        previous_fix = fix_type
        previous_satellites = satellites
        previous_spoofing = spoofing
        previous_jamming = jamming

    return events


# ============================================================
# MAIN
# ============================================================

def reconstruct_timeline():

    print("=" * 70)
    print("PX4 FORENSIC TIMELINE RECONSTRUCTION")
    print("=" * 70)

    if not EVIDENCE_FILE.exists():

        raise FileNotFoundError(
            f"Evidence file not found: {EVIDENCE_FILE}"
        )

    print(f"\nEvidence:")
    print(EVIDENCE_FILE)

    print("\nLoading ULog...")

    ulog = ULog(
        str(EVIDENCE_FILE)
    )

    events = []

    print("Extracting vehicle status events...")

    events.extend(
        extract_vehicle_status_events(ulog)
    )

    print("Extracting landing/takeoff events...")

    events.extend(
        extract_land_events(ulog)
    )

    print("Extracting vehicle commands...")

    events.extend(
        extract_command_events(ulog)
    )

    print("Extracting command acknowledgements...")

    events.extend(
        extract_command_ack_events(ulog)
    )

    print("Extracting GPS state events...")

    events.extend(
        extract_gps_events(ulog)
    )

    # --------------------------------------------------------
    # Sort chronologically
    # --------------------------------------------------------

    events.sort(
        key=lambda event: event["timestamp_us"]
    )

    # --------------------------------------------------------
    # Timeline metadata
    # --------------------------------------------------------

    timeline = {

        "case_id": CASE_ID,

        "evidence_id": EVIDENCE_ID,

        "source": str(EVIDENCE_FILE),

        "event_count": len(events),

        "timeline_start_us": (
            events[0]["timestamp_us"]
            if events
            else None
        ),

        "timeline_end_us": (
            events[-1]["timestamp_us"]
            if events
            else None
        ),

        "events": events,

        "forensic_note":
            "Events represent observations reconstructed "
            "from recorded PX4 telemetry. Event classification "
            "does not by itself establish causality or malicious activity."
    }

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w"
    ) as f:

        json.dump(
            timeline,
            f,
            indent=4
        )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    event_types = {}

    for event in events:

        event_type = event["event_type"]

        event_types[event_type] = (
            event_types.get(event_type, 0) + 1
        )

    print("\nTimeline summary:")
    print(
        json.dumps(
            event_types,
            indent=4
        )
    )

    print(
        f"\nTotal events: {len(events)}"
    )

    print(
        f"\nOutput:\n{OUTPUT_FILE}"
    )

    print("\nFirst 10 events:")

    for event in events[:10]:

        print(
            f"{event['timestamp_seconds']:12.3f}s  "
            f"{event['event_type']}"
        )

    print("\nLast 10 events:")

    for event in events[-10:]:

        print(
            f"{event['timestamp_seconds']:12.3f}s  "
            f"{event['event_type']}"
        )

    print("\n" + "=" * 70)


if __name__ == "__main__":
    reconstruct_timeline()
