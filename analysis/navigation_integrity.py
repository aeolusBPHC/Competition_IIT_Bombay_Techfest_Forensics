import json
from pathlib import Path
from statistics import mean


# ============================================================
# CONFIGURATION
# ============================================================

CASE_ID = "CASE-001"
EVIDENCE_ID = "EVD-20260919-175126"

BASE_DIR = Path("repository/cases") / CASE_ID / EVIDENCE_ID
GPS_FILE = BASE_DIR / "analysis" / "gps_data.json"
OUTPUT_FILE = BASE_DIR / "analysis" / "navigation_integrity.json"


# ============================================================
# LOAD GPS DATA
# ============================================================

def load_gps_data():

    if not GPS_FILE.exists():
        raise FileNotFoundError(
            f"GPS data not found: {GPS_FILE}"
        )

    with open(GPS_FILE, "r") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("GPS JSON must contain a list of records.")

    return data


# ============================================================
# STATE COUNTS
# ============================================================

def count_states(data, field):

    counts = {}

    for record in data:

        value = record.get(field)

        if value is None:
            continue

        value = str(value)

        counts[value] = counts.get(value, 0) + 1

    return counts


# ============================================================
# STATE TRANSITIONS
# ============================================================

def find_state_transitions(data, field):

    transitions = []

    if not data:
        return transitions

    previous = data[0].get(field)

    for record in data[1:]:

        current = record.get(field)

        if current != previous:

            transitions.append({
                "timestamp_us": record.get("timestamp"),
                "field": field,
                "from": previous,
                "to": current
            })

            previous = current

    return transitions


# ============================================================
# POSITION JUMP ANALYSIS
# ============================================================

def calculate_position_jumps(data):

    jumps = []

    for i in range(1, len(data)):

        previous = data[i - 1]
        current = data[i]

        lat1 = previous.get("latitude_deg")
        lon1 = previous.get("longitude_deg")

        lat2 = current.get("latitude_deg")
        lon2 = current.get("longitude_deg")

        if None in (lat1, lon1, lat2, lon2):
            continue

        # Approximate conversion:
        # 1 degree latitude ≈ 111,320 m
        # longitude depends on latitude.
        import math

        dlat = (lat2 - lat1) * 111320

        dlon = (
            (lon2 - lon1)
            * 111320
            * math.cos(math.radians(lat1))
        )

        distance_m = math.sqrt(
            dlat ** 2 + dlon ** 2
        )

        jumps.append({
            "timestamp_us": current.get("timestamp"),
            "distance_from_previous_m": distance_m
        })

    return jumps


# ============================================================
# QUALITY STATISTICS
# ============================================================

def statistics(data, field):

    values = [
        record[field]
        for record in data
        if record.get(field) is not None
    ]

    if not values:
        return {
            "min": None,
            "max": None,
            "average": None
        }

    return {
        "min": min(values),
        "max": max(values),
        "average": mean(values)
    }


# ============================================================
# MAIN ANALYSIS
# ============================================================

def analyze():

    data = load_gps_data()

    print("=" * 70)
    print("PX4 NAVIGATION INTEGRITY ANALYSIS")
    print("=" * 70)

    print(f"\nGPS samples: {len(data)}")

    # --------------------------------------------------------
    # GPS state distributions
    # --------------------------------------------------------

    spoofing_states = count_states(
        data,
        "spoofing_state"
    )

    jamming_states = count_states(
        data,
        "jamming_state"
    )

    jamming_indicators = count_states(
        data,
        "jamming_indicator"
    )

    authentication_states = count_states(
        data,
        "authentication_state"
    )

    fix_types = count_states(
        data,
        "fix_type"
    )

    # --------------------------------------------------------
    # State transitions
    # --------------------------------------------------------

    spoofing_transitions = find_state_transitions(
        data,
        "spoofing_state"
    )

    jamming_transitions = find_state_transitions(
        data,
        "jamming_state"
    )

    fix_transitions = find_state_transitions(
        data,
        "fix_type"
    )

    satellite_transitions = find_state_transitions(
        data,
        "satellites_used"
    )

    # --------------------------------------------------------
    # Position movement
    # --------------------------------------------------------

    position_jumps = calculate_position_jumps(data)

    jump_distances = [
        x["distance_from_previous_m"]
        for x in position_jumps
    ]

    if jump_distances:

        max_jump = max(jump_distances)

        average_jump = mean(jump_distances)

    else:

        max_jump = None
        average_jump = None

    # --------------------------------------------------------
    # Quality statistics
    # --------------------------------------------------------

    hdop_stats = statistics(
        data,
        "hdop"
    )

    vdop_stats = statistics(
        data,
        "vdop"
    )

    satellites_stats = statistics(
        data,
        "satellites_used"
    )

    speed_stats = statistics(
        data,
        "vel_m_s"
    )

    # --------------------------------------------------------
    # Integrity observations
    # --------------------------------------------------------

    observations = []

    if spoofing_states == {"0": len(data)}:

        observations.append(
            "No asserted GPS spoofing state was observed "
            "in the recorded GPS samples."
        )

    else:

        observations.append(
            "One or more GPS spoofing-state values other than "
            "0 were observed."
        )

    if jamming_states == {"0": len(data)}:

        observations.append(
            "No asserted GPS jamming state was observed "
            "in the recorded GPS samples."
        )

    else:

        observations.append(
            "One or more GPS jamming-state values other than "
            "0 were observed."
        )

    if len(fix_types) == 1:

        observations.append(
            "GPS fix type remained unchanged throughout "
            "the analyzed GPS records."
        )

    else:

        observations.append(
            "GPS fix type changed during the recording."
        )

    if len(satellite_transitions) == 0:

        observations.append(
            "Satellite count did not change during the "
            "analyzed GPS records."
        )

    else:

        observations.append(
            "Satellite count changed during the recording."
        )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    result = {

        "case_id": CASE_ID,

        "evidence_id": EVIDENCE_ID,

        "source": str(GPS_FILE),

        "sample_count": len(data),

        "gps_state_distribution": {

            "spoofing_state": spoofing_states,

            "jamming_state": jamming_states,

            "jamming_indicator": jamming_indicators,

            "authentication_state":
                authentication_states,

            "fix_type": fix_types
        },

        "state_transitions": {

            "spoofing": spoofing_transitions,

            "jamming": jamming_transitions,

            "fix_type": fix_transitions,

            "satellites": satellite_transitions
        },

        "gps_quality": {

            "satellites": satellites_stats,

            "hdop": hdop_stats,

            "vdop": vdop_stats,

            "speed_m_s": speed_stats
        },

        "position_analysis": {

            "samples_analyzed":
                len(position_jumps),

            "maximum_consecutive_position_change_m":
                max_jump,

            "average_consecutive_position_change_m":
                average_jump
        },

        "observations": observations,

        "forensic_note":
            "Navigation state observations are derived from "
            "recorded PX4 telemetry. They should not by "
            "themselves be interpreted as proof or exclusion "
            "of a cyberattack."
    }

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    with open(OUTPUT_FILE, "w") as f:

        json.dump(
            result,
            f,
            indent=4
        )

    print("\nGPS state distribution:")

    print(
        json.dumps(
            result["gps_state_distribution"],
            indent=4
        )
    )

    print("\nState transitions:")

    print(
        json.dumps(
            result["state_transitions"],
            indent=4
        )
    )

    print("\nPosition analysis:")

    print(
        json.dumps(
            result["position_analysis"],
            indent=4
        )
    )

    print("\nObservations:")

    for observation in observations:

        print(f"- {observation}")

    print("\nOutput:")

    print(OUTPUT_FILE)

    print("\n" + "=" * 70)


if __name__ == "__main__":
    analyze()
