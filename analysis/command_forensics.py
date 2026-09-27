from pathlib import Path
from pyulog import ULog
import json


# ============================================================
# CONFIGURATION
# ============================================================

CASE_ID = "CASE-001"
EVIDENCE_ID = "EVD-20260919-175126"

BASE_DIR = (
    Path("repository/cases")
    / CASE_ID
    / EVIDENCE_ID
)

EVIDENCE_FILE = (
    BASE_DIR
    / "evidence"
    / "17_02_27.ulg"
)

OUTPUT_FILE = (
    BASE_DIR
    / "analysis"
    / "command_forensics.json"
)


# ============================================================
# SAFE VALUE CONVERSION
# ============================================================

def convert_value(value):

    if hasattr(value, "item"):
        return value.item()

    return value


# ============================================================
# EXTRACT VEHICLE COMMANDS
# ============================================================

def extract_commands(ulog):

    dataset = ulog.get_dataset(
        "vehicle_command"
    )

    data = dataset.data

    commands = []

    for i in range(len(data["timestamp"])):

        record = {}

        for field in data.keys():

            record[field] = convert_value(
                data[field][i]
            )

        commands.append(record)

    return commands


# ============================================================
# EXTRACT COMMAND ACKS
# ============================================================

def extract_acks(ulog):

    dataset = ulog.get_dataset(
        "vehicle_command_ack"
    )

    data = dataset.data

    acknowledgements = []

    for i in range(len(data["timestamp"])):

        record = {}

        for field in data.keys():

            record[field] = convert_value(
                data[field][i]
            )

        acknowledgements.append(record)

    return acknowledgements


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("PX4 COMMAND FORENSIC EXTRACTION")
    print("=" * 70)

    print("\nEvidence:")
    print(EVIDENCE_FILE)

    ulog = ULog(
        str(EVIDENCE_FILE)
    )

    commands = extract_commands(ulog)

    acknowledgements = extract_acks(ulog)

    result = {

        "case_id": CASE_ID,

        "evidence_id": EVIDENCE_ID,

        "source": str(EVIDENCE_FILE),

        "vehicle_command_count": len(commands),

        "command_ack_count": len(acknowledgements),

        "vehicle_commands": commands,

        "command_acknowledgements": acknowledgements,

        "forensic_note":
            "Command IDs and parameters are preserved "
            "as recorded in the PX4 ULog. Semantic "
            "interpretation must be based on the applicable "
            "PX4 command definitions and should not replace "
            "the original recorded values."
    }

    with open(
        OUTPUT_FILE,
        "w"
    ) as f:

        json.dump(
            result,
            f,
            indent=4
        )

    print(
        f"\nVehicle commands: "
        f"{len(commands)}"
    )

    print(
        f"Command acknowledgements: "
        f"{len(acknowledgements)}"
    )

    print("\nCommands:")

    for command in commands:

        print(
            f"  {command['timestamp'] / 1_000_000:10.3f}s "
            f"command={command['command']}"
        )

    print("\nAcknowledgements:")

    for ack in acknowledgements:

        print(
            f"  {ack['timestamp'] / 1_000_000:10.3f}s "
            f"command={ack['command']} "
            f"result={ack['result']}"
        )

    print(
        f"\nOutput:\n{OUTPUT_FILE}"
    )

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
