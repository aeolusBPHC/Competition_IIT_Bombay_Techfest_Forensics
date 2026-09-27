from pathlib import Path
import json

from pyulog import ULog


CASE_ID = "CASE-001"
EVIDENCE_ID = "EVD-20260919-175126"

EVIDENCE_PATH = Path(
    "repository/cases/CASE-001/"
    "EVD-20260919-175126/"
    "evidence/17_02_27.ulg"
)

OUTPUT_PATH = Path(
    "repository/cases/CASE-001/"
    "EVD-20260919-175126/"
    "analysis/state_reconstruction.json"
)


def get_dataset(ulog, name):
    return next(
        (dataset for dataset in ulog.data_list if dataset.name == name),
        None
    )


def to_python(value):
    if hasattr(value, "item"):
        return value.item()
    return value


def make_transition_events(
    dataset,
    field,
    event_type
):
    events = []

    if dataset is None:
        return events

    data = dataset.data

    if "timestamp" not in data or field not in data:
        return events

    timestamps = data["timestamp"]
    values = data[field]

    if len(timestamps) == 0:
        return events

    previous = to_python(values[0])

    for i in range(1, len(timestamps)):
        current = to_python(values[i])

        if current != previous:
            events.append({
                "timestamp_us": int(timestamps[i]),
                "timestamp_seconds": float(timestamps[i] / 1e6),
                "event_type": event_type,
                "source_dataset": dataset.name,
                "field": field,
                "previous_value": previous,
                "new_value": current
            })

            previous = current

    return events


def make_initial_state(dataset, fields):
    if dataset is None:
        return None

    data = dataset.data

    if "timestamp" not in data or len(data["timestamp"]) == 0:
        return None

    index = 0

    state = {
        "timestamp_us": int(data["timestamp"][index]),
        "timestamp_seconds": float(
            data["timestamp"][index] / 1e6
        )
    }

    for field in fields:
        if field in data:
            state[field] = to_python(data[field][index])

    return state


def main():

    print("=" * 70)
    print("PX4 STATE RECONSTRUCTION")
    print("=" * 70)

    print("\nEvidence:")
    print(EVIDENCE_PATH)

    if not EVIDENCE_PATH.exists():
        raise FileNotFoundError(
            f"Evidence file not found: {EVIDENCE_PATH}"
        )

    print("\nLoading ULog...")
    ulog = ULog(str(EVIDENCE_PATH))

    vehicle_status = get_dataset(
        ulog,
        "vehicle_status"
    )

    land_detected = get_dataset(
        ulog,
        "vehicle_land_detected"
    )

    events = []

    # ------------------------------------------------------------
    # VEHICLE STATUS
    # ------------------------------------------------------------

    print("Extracting vehicle-status transitions...")

    status_fields = {
        "arming_state":
            "ARMING_STATE_CHANGE",

        "nav_state":
            "NAVIGATION_STATE_CHANGE",

        "failsafe":
            "FAILSAFE_STATE_CHANGE",

        "gcs_connection_lost":
            "GCS_CONNECTION_STATE_CHANGE",

        "safety_off":
            "SAFETY_STATE_CHANGE",

        "power_input_valid":
            "POWER_INPUT_STATE_CHANGE",

        "pre_flight_checks_pass":
            "PREFLIGHT_CHECK_STATE_CHANGE"
    }

    for field, event_type in status_fields.items():

        events.extend(
            make_transition_events(
                vehicle_status,
                field,
                event_type
            )
        )

    initial_vehicle_status = make_initial_state(
        vehicle_status,
        [
            "arming_state",
            "nav_state",
            "failsafe",
            "gcs_connection_lost",
            "safety_off",
            "power_input_valid",
            "pre_flight_checks_pass"
        ]
    )

    # ------------------------------------------------------------
    # LAND DETECTION
    # ------------------------------------------------------------

    print("Extracting land-detection transitions...")

    land_fields = {
        "landed":
            "LAND_DETECTION_STATE_CHANGE",

        "ground_contact":
            "GROUND_CONTACT_STATE_CHANGE",

        "maybe_landed":
            "MAYBE_LANDED_STATE_CHANGE",

        "in_descend":
            "DESCEND_STATE_CHANGE",

        "at_rest":
            "AT_REST_STATE_CHANGE"
    }

    for field, event_type in land_fields.items():

        events.extend(
            make_transition_events(
                land_detected,
                field,
                event_type
            )
        )

    initial_land_state = make_initial_state(
        land_detected,
        [
            "landed",
            "ground_contact",
            "maybe_landed",
            "in_ground_effect",
            "in_descend",
            "has_low_throttle",
            "at_rest"
        ]
    )

    # ------------------------------------------------------------
    # SORT
    # ------------------------------------------------------------

    events.sort(
        key=lambda event: event["timestamp_us"]
    )

    result = {
        "case_id": CASE_ID,
        "evidence_id": EVIDENCE_ID,
        "source": str(EVIDENCE_PATH),

        "initial_vehicle_status":
            initial_vehicle_status,

        "initial_land_detection":
            initial_land_state,

        "event_count":
            len(events),

        "events":
            events
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            result,
            f,
            indent=2
        )

    print("\nState reconstruction summary:")

    counts = {}

    for event in events:
        event_type = event["event_type"]
        counts[event_type] = (
            counts.get(event_type, 0) + 1
        )

    print(
        json.dumps(
            counts,
            indent=4
        )
    )

    print(
        f"\nTotal state events: {len(events)}"
    )

    print("\nOutput:")
    print(OUTPUT_PATH)

    print("\nFirst 10 state events:")

    for event in events[:10]:
        print(
            f"{event['timestamp_seconds']:10.3f}s "
            f"{event['event_type']:35s} "
            f"{event['previous_value']} -> "
            f"{event['new_value']}"
        )


if __name__ == "__main__":
    main()
