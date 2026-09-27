import json
import os
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
    f"{ANALYSIS_DIR}/command_ack_matching.json"
)


# ============================================================
# HELPERS
# ============================================================

def scalar(value):
    """Convert NumPy scalar values to native Python values."""
    if hasattr(value, "item"):
        return value.item()
    return value


def dataset_rows(data):
    """Convert pyulog column-oriented data into row dictionaries."""

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


# ============================================================
# LOAD ULOG
# ============================================================

if not os.path.exists(EVIDENCE_FILE):
    raise FileNotFoundError(EVIDENCE_FILE)

ulog = ULog(EVIDENCE_FILE)


command_dataset = ulog.get_dataset("vehicle_command")
ack_dataset = ulog.get_dataset("vehicle_command_ack")


commands = dataset_rows(command_dataset.data)
acks = dataset_rows(ack_dataset.data)


# ============================================================
# COMMAND NAME DECODING
# ============================================================

COMMAND_NAMES = {
    211: "VEHICLE_CMD_DO_GRIPPER",
    512: "VEHICLE_CMD_REQUEST_MESSAGE",
    521: "VEHICLE_CMD_REQUEST_CAMERA_INFORMATION",
}


def command_name(command_id):
    return COMMAND_NAMES.get(
        command_id,
        f"UNKNOWN_COMMAND_{command_id}"
    )


# ============================================================
# INDEX ACKS BY COMMAND ID
# ============================================================

acks_by_command = {}

for ack_index, ack in enumerate(acks):

    command_id = int(ack["command"])

    acks_by_command.setdefault(
        command_id,
        []
    ).append(
        {
            "ack_index": ack_index,
            "timestamp_us": int(ack["timestamp"]),
            "timestamp_seconds": ack["timestamp"] / 1_000_000.0,
            "command": command_id,
            "command_name": command_name(command_id),
            "result": int(ack["result"]),
            "result_param1": int(ack["result_param1"]),
            "result_param2": int(ack["result_param2"]),
            "target_system": int(ack["target_system"]),
            "target_component": int(ack["target_component"]),
            "from_external": int(ack["from_external"]),
        }
    )


# ============================================================
# MATCH COMMANDS TO ACKS
# ============================================================

matched = []
unmatched_commands = []

for command_index, command in enumerate(commands):

    command_id = int(command["command"])
    command_time_us = int(command["timestamp"])

    candidates = acks_by_command.get(
        command_id,
        []
    )

    if not candidates:

        unmatched_commands.append(
            {
                "command_index": command_index,
                "timestamp_us": command_time_us,
                "timestamp_seconds": command_time_us / 1_000_000.0,
                "command": command_id,
                "command_name": command_name(command_id),
                "status": "NO_ACK_WITH_SAME_COMMAND_ID",
                "source_system": int(command["source_system"]),
                "source_component": int(command["source_component"]),
                "target_system": int(command["target_system"]),
                "target_component": int(command["target_component"]),
                "confirmation": int(command["confirmation"]),
                "from_external": int(command["from_external"]),
            }
        )

        continue

    # --------------------------------------------------------
    # Find temporally closest ACK among SAME command IDs
    # --------------------------------------------------------

    best_ack = min(
        candidates,
        key=lambda ack: abs(
            ack["timestamp_us"] - command_time_us
        )
    )

        # --------------------------------------------------------
    # Preserve ALL same-command-ID ACK candidates
    # --------------------------------------------------------

    ack_candidates = []

    for ack in candidates:

        delta_us = (
            ack["timestamp_us"]
            - command_time_us
        )

        candidate = dict(ack)

        candidate["delta_us"] = delta_us

        candidate["delta_seconds"] = (
            delta_us / 1_000_000.0
        )

        candidate["ack_after_command"] = (
            delta_us >= 0
        )

        ack_candidates.append(candidate)

    # Closest candidate is useful for analysis,
    # but is NOT treated as definitive causality.

    closest_ack = min(
        ack_candidates,
        key=lambda ack: abs(ack["delta_us"])
    )

    matched.append(
        {
            "command_index": command_index,

            "command_timestamp_us":
                command_time_us,

            "command_timestamp_seconds":
                command_time_us / 1_000_000.0,

            "command":
                command_id,

            "command_name":
                command_name(command_id),

            "source_system":
                int(command["source_system"]),

            "source_component":
                int(command["source_component"]),

            "target_system":
                int(command["target_system"]),

            "target_component":
                int(command["target_component"]),

            "confirmation":
                int(command["confirmation"]),

            "from_external":
                int(command["from_external"]),

            "same_command_id_ack_count":
                len(ack_candidates),

            "ack_candidates":
                ack_candidates,

            "closest_ack":
                closest_ack,

            "matching_basis":
                "SAME_COMMAND_ID",

            "causality_status":
                "CANDIDATE_MATCH_ONLY",
        }
    )


# ============================================================
# ACKS WITH NO COMMAND
# ============================================================

matched_ack_indices = set()

for item in matched:

    for ack in item["ack_candidates"]:

        matched_ack_indices.add(
            ack["ack_index"]
        )

unmatched_acks = []

for ack_index, ack in enumerate(acks):

    if ack_index in matched_ack_indices:
        continue

    unmatched_acks.append(
        {
            "ack_index": ack_index,
            "timestamp_us": int(ack["timestamp"]),
            "timestamp_seconds":
                ack["timestamp"] / 1_000_000.0,
            "command": int(ack["command"]),
            "command_name":
                command_name(int(ack["command"])),
            "result": int(ack["result"]),
            "result_param1":
                int(ack["result_param1"]),
            "result_param2":
                int(ack["result_param2"]),
            "target_system":
                int(ack["target_system"]),
            "target_component":
                int(ack["target_component"]),
            "from_external":
                int(ack["from_external"]),
            "status":
                "NO_COMMAND_WITH_SAME_COMMAND_ID",
        }
    )


# ============================================================
# COMMAND ID SUMMARY
# ============================================================

command_ids = {}

for command in commands:

    command_id = int(command["command"])

    command_ids.setdefault(
        command_id,
        {
            "command_name":
                command_name(command_id),
            "command_count": 0,
            "ack_count_same_id":
                len(acks_by_command.get(command_id, [])),
        }
    )

    command_ids[command_id]["command_count"] += 1


ack_ids = {}

for ack in acks:

    command_id = int(ack["command"])

    ack_ids.setdefault(
        command_id,
        {
            "command_name":
                command_name(command_id),
            "ack_count": 0,
        }
    )

    ack_ids[command_id]["ack_count"] += 1


# ============================================================
# FORENSIC OBSERVATIONS
# ============================================================

observations = []

for command_id, info in command_ids.items():

    if info["ack_count_same_id"] == 0:

        observations.append(
            {
                "type":
                    "COMMAND_WITHOUT_SAME_ID_ACK",

                "command":
                    command_id,

                "command_name":
                    info["command_name"],

                "command_count":
                    info["command_count"],

                "observation":
                    (
                        "Commands with this command ID were "
                        "recorded, but no vehicle_command_ack "
                        "records with the same command ID were "
                        "found in the analyzed ULog."
                    )
            }
        )


for ack_command_id, info in ack_ids.items():

    command_count = command_ids.get(
        ack_command_id,
        {}
    ).get(
        "command_count",
        0
    )

    if command_count == 0:

        observations.append(
            {
                "type":
                    "ACK_WITHOUT_SAME_ID_COMMAND",

                "command":
                    ack_command_id,

                "command_name":
                    info["command_name"],

                "ack_count":
                    info["ack_count"],

                "observation":
                    (
                        "vehicle_command_ack records with "
                        "this command ID were recorded, but "
                        "no vehicle_command records with the "
                        "same command ID were found in the "
                        "analyzed ULog."
                    )
            }
        )


# ============================================================
# OUTPUT
# ============================================================

result = {

    "case_id": CASE_ID,

    "evidence_id": EVIDENCE_ID,

    "source": EVIDENCE_FILE,

    "command_count": len(commands),

    "ack_count": len(acks),

    "command_id_summary": command_ids,

    "ack_id_summary": ack_ids,

    "matched_same_command_id": matched,

    "unmatched_commands": unmatched_commands,

    "unmatched_acks": unmatched_acks,

    "observations": observations,
}


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
# TERMINAL SUMMARY
# ============================================================

print("=" * 70)
print("PX4 COMMAND / ACK FORENSIC MATCHING")
print("=" * 70)

print()
print(f"Commands: {len(commands)}")
print(f"ACKs:     {len(acks)}")

print()
print("Command IDs:")

for command_id, info in command_ids.items():

    print(
        f"  {command_id}: "
        f"{info['command_name']} "
        f"commands={info['command_count']} "
        f"same-ID-ACKs={info['ack_count_same_id']}"
    )


print()
print("ACK IDs:")

for command_id, info in ack_ids.items():

    print(
        f"  {command_id}: "
        f"{info['command_name']} "
        f"ACKs={info['ack_count']}"
    )


print()
print(
    "Same-command-ID matches:",
    len(matched)
)

print(
    "Commands without same-ID ACK:",
    len(unmatched_commands)
)

print(
    "ACKs without same-ID command:",
    len(unmatched_acks)
)

print()
print("Output:")
print(OUTPUT_FILE)
