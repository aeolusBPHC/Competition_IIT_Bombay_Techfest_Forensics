from pathlib import Path
import json


CASE_ID = "CASE-001"
EVIDENCE_ID = "EVD-20260919-175126"

ANALYSIS_DIR = Path(
    "repository/cases/CASE-001/"
    "EVD-20260919-175126/analysis"
)

TIMELINE_PATH = ANALYSIS_DIR / "forensic_timeline.json"
STATE_PATH = ANALYSIS_DIR / "state_reconstruction.json"
GPS_ANALYSIS_PATH = ANALYSIS_DIR / "gps_analysis.json"
NAVIGATION_PATH = ANALYSIS_DIR / "navigation_integrity.json"

OUTPUT_PATH = ANALYSIS_DIR / "event_correlations.json"


# Correlation windows in seconds.
CORRELATION_WINDOWS = {
    "tight": 0.1,
    "short": 0.5,
    "medium": 1.0,
    "wide": 5.0
}


def load_json(path):
    if not path.exists():
        print(f"WARNING: file not found: {path}")
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_timeline_events(data):
    if not data:
        return []

    return data.get("events", [])


def get_state_events(data):
    if not data:
        return []

    return data.get("events", [])


def normalize_timeline_event(event):
    """
    Convert timeline event representation into a common format.
    """
    return {
        "timestamp_seconds": float(event["timestamp_seconds"]),
        "event_type": event.get("event_type", "UNKNOWN"),
        "source_dataset": event.get("source_dataset"),
        "field": event.get("field"),
        "details": event.get("details", {})
    }


def normalize_state_event(event):
    """
    Convert state reconstruction event representation into
    the same event representation used by the correlation engine.
    """
    return {
        "timestamp_seconds": float(event["timestamp_seconds"]),
        "event_type": event.get("event_type", "UNKNOWN"),
        "source_dataset": event.get("source_dataset"),
        "field": event.get("field"),
        "details": {
            "previous_value": event.get("previous_value"),
            "new_value": event.get("new_value")
        }
    }


def build_unified_events(timeline_data, state_data):
    """
    Construct the unified forensic event stream.

    Source-of-truth policy:

    forensic_timeline.json:
        - VEHICLE_COMMAND
        - COMMAND_ACK

    state_reconstruction.json:
        - state transition events

    This avoids merging two derived files that contain
    overlapping state transitions.
    """

    events = []

    # ------------------------------------------------------------
    # Timeline: retain command-related events only
    # ------------------------------------------------------------

    for event in get_timeline_events(timeline_data):

        event_type = event.get("event_type")

        if event_type not in {
            "VEHICLE_COMMAND",
            "COMMAND_ACK"
        }:
            continue

        events.append(
            normalize_timeline_event(event)
        )

    # ------------------------------------------------------------
    # State reconstruction: retain all state transitions
    # ------------------------------------------------------------

    for event in get_state_events(state_data):

        events.append(
            normalize_state_event(event)
        )

    # ------------------------------------------------------------
    # Sort chronologically
    # ------------------------------------------------------------

    events.sort(
        key=lambda x: x["timestamp_seconds"]
    )

    return events
 
def find_nearby_events(events, target_index, window):
    """
    Find events within ±window seconds of the target event.
    """
    target = events[target_index]
    target_time = target["timestamp_seconds"]

    nearby = []

    for i, event in enumerate(events):
        if i == target_index:
            continue

        delta = event["timestamp_seconds"] - target_time

        if abs(delta) <= window:
            nearby.append({
                "event_index": i,
                "timestamp_seconds": event["timestamp_seconds"],
                "delta_seconds": round(delta, 6),
                "event_type": event["event_type"],
                "source_dataset": event.get("source_dataset"),
                "field": event.get("field"),
                "details": event.get("details", {})
            })

    nearby.sort(key=lambda x: abs(x["delta_seconds"]))

    return nearby


def is_interesting_event(event):
    """
    Events that are particularly useful for security-oriented
    forensic correlation.
    """
    interesting_types = {
        "GCS_CONNECTION_STATE_CHANGE",
        "GPS_STATE_CHANGE",
        "GPS_INTEGRITY_EVENT",
        "PREFLIGHT_CHECK_STATE_CHANGE",
        "FAILSAFE_STATE_CHANGE",
        "NAVIGATION_STATE_CHANGE",
        "ARMING_STATE_CHANGE",
        "LAND_DETECTION_STATE_CHANGE",
        "DESCEND_STATE_CHANGE",
        "VEHICLE_COMMAND",
        "COMMAND_ACK",
        "POWER_INPUT_STATE_CHANGE",
        "SAFETY_STATE_CHANGE"
    }

    return event["event_type"] in interesting_types


def classify_relationship(target, nearby):
    """
    Classify only temporal proximity.

    This function deliberately does NOT infer causality.
    """
    if not nearby:
        return "NO_NEARBY_EVENTS"

    event_types = {event["event_type"] for event in nearby}

    if (
        target["event_type"] == "GCS_CONNECTION_STATE_CHANGE"
        and "DESCEND_STATE_CHANGE" in event_types
    ):
        return "GCS_AND_DESCEND_TEMPORAL_PROXIMITY"

    if (
        target["event_type"] == "GCS_CONNECTION_STATE_CHANGE"
        and (
            "FAILSAFE_STATE_CHANGE" in event_types
            or "NAVIGATION_STATE_CHANGE" in event_types
        )
    ):
        return "GCS_AND_FLIGHT_STATE_TEMPORAL_PROXIMITY"

    if (
        target["event_type"] == "VEHICLE_COMMAND"
        and "COMMAND_ACK" in event_types
    ):
        return "COMMAND_ACK_TEMPORAL_PROXIMITY"

    if (
        target["event_type"] == "PREFLIGHT_CHECK_STATE_CHANGE"
        and (
            "GPS_STATE_CHANGE" in event_types
            or "GPS_INTEGRITY_EVENT" in event_types
        )
    ):
        return "PREFLIGHT_AND_GPS_TEMPORAL_PROXIMITY"

    return "GENERAL_TEMPORAL_PROXIMITY"


def build_correlations(events):
    correlations = []

    for index, target in enumerate(events):

        if not is_interesting_event(target):
            continue

        for window_name, window in CORRELATION_WINDOWS.items():

            nearby = find_nearby_events(
                events,
                index,
                window
            )

            if not nearby:
                continue

            relationship = classify_relationship(
                target,
                nearby
            )

            correlations.append({
                "target_event": {
                    "event_index": index,
                    "timestamp_seconds": target["timestamp_seconds"],
                    "event_type": target["event_type"],
                    "source_dataset": target.get("source_dataset"),
                    "field": target.get("field"),
                    "details": target.get("details", {})
                },
                "window": {
                    "name": window_name,
                    "seconds": window
                },
                "relationship": relationship,
                "causality_established": False,
                "nearby_events": nearby
            })

    return correlations


def build_security_summary(events, correlations):
    summary = {
        "total_unified_events": len(events),
        "total_correlations": len(correlations),
        "event_type_counts": {},
        "relationship_counts": {}
    }

    for event in events:
        event_type = event["event_type"]

        summary["event_type_counts"][event_type] = (
            summary["event_type_counts"].get(event_type, 0) + 1
        )

    for correlation in correlations:
        relationship = correlation["relationship"]

        summary["relationship_counts"][relationship] = (
            summary["relationship_counts"].get(relationship, 0) + 1
        )

    return summary


def main():

    print("=" * 70)
    print("PX4 FORENSIC EVENT CORRELATION")
    print("=" * 70)

    print("\nAnalysis directory:")
    print(ANALYSIS_DIR)

    timeline_data = load_json(TIMELINE_PATH)
    state_data = load_json(STATE_PATH)

    # These are loaded now so that later versions can incorporate
    # GPS/navigation findings directly into the correlation engine.
    gps_analysis = load_json(GPS_ANALYSIS_PATH)
    navigation_analysis = load_json(NAVIGATION_PATH)

    print("\nBuilding unified event stream...")

    events = build_unified_events(
        timeline_data,
        state_data
    )

    print(f"Unified events: {len(events)}")

    print("\nGenerating temporal correlations...")

    correlations = build_correlations(events)

    print(f"Correlations: {len(correlations)}")

    summary = build_security_summary(
        events,
        correlations
    )

    result = {
        "case_id": CASE_ID,
        "evidence_id": EVIDENCE_ID,

        "methodology": {
            "description": (
                "Temporal correlation of independently extracted PX4 "
                "forensic events."
            ),
            "causality_policy": (
                "Temporal proximity does not establish causality."
            ),
            "correlation_windows_seconds": CORRELATION_WINDOWS
        },

        "source_files": {
            "forensic_timeline": str(TIMELINE_PATH),
            "state_reconstruction": str(STATE_PATH),
            "gps_analysis": str(GPS_ANALYSIS_PATH),
            "navigation_integrity": str(NAVIGATION_PATH)
        },

        "summary": summary,

        "events": events,

        "correlations": correlations
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

    print("\n" + "=" * 70)
    print("CORRELATION SUMMARY")
    print("=" * 70)

    print(
        json.dumps(
            summary,
            indent=4
        )
    )

    print("\nOutput:")
    print(OUTPUT_PATH)

    

    important = [
    correlation
    for correlation in correlations
    if correlation["relationship"]
    in {
        "GCS_AND_DESCEND_TEMPORAL_PROXIMITY",
        "GCS_AND_FLIGHT_STATE_TEMPORAL_PROXIMITY",
        "COMMAND_ACK_TEMPORAL_PROXIMITY"
    }
]

    print("\nImportant correlated events:")

    # Keep only the closest correlation for each target event.
    best_correlations = {}

    for correlation in correlations:

        relationship = correlation["relationship"]

        if relationship not in {
            "GCS_AND_DESCEND_TEMPORAL_PROXIMITY",
            "GCS_AND_FLIGHT_STATE_TEMPORAL_PROXIMITY",
            "COMMAND_ACK_TEMPORAL_PROXIMITY"
        }:
            continue

        target = correlation["target_event"]

        target_key = (
            round(target["timestamp_seconds"], 6),
            target["event_type"],
            target.get("source_dataset"),
            target.get("field")
        )

        # Calculate nearest neighboring event.
        nearby = correlation["nearby_events"]

        if not nearby:
            continue

        closest_distance = min(
            abs(event["delta_seconds"])
            for event in nearby
        )

        if target_key not in best_correlations:
            best_correlations[target_key] = (
                closest_distance,
                correlation
            )

        elif closest_distance < best_correlations[target_key][0]:
            best_correlations[target_key] = (
                closest_distance,
                correlation
            )

    for _, (_, correlation) in sorted(
        best_correlations.items(),
        key=lambda item: item[1][1]["target_event"]["timestamp_seconds"]
    ):

        target = correlation["target_event"]

        print(
            f"\n{target['timestamp_seconds']:10.3f}s "
            f"{target['event_type']}"
        )

        print(
            f"  relationship: "
            f"{correlation['relationship']}"
        )

        for event in correlation["nearby_events"]:

            if abs(event["delta_seconds"]) > 1.0:
                continue

            print(
                f"    {event['timestamp_seconds']:10.3f}s "
                f"{event['event_type']:35s} "
                f"Δ={event['delta_seconds']:+.3f}s"
            )

if __name__ == "__main__":
    main()
