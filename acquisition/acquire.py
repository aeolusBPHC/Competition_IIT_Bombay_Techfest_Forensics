import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def calculate_sha256(file_path, chunk_size=1024 * 1024):
    """
    Calculate SHA-256 hash of a file.

    The file is read in chunks so that very large evidence files
    can be processed without loading the entire file into memory.
    """

    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def utc_timestamp():
    """
    Return the current UTC timestamp in ISO-8601 format.
    """

    return datetime.now(timezone.utc).isoformat()


def acquire_evidence(input_file, case_id, operator="drone_forensics"):
    """
    Acquire a piece of digital evidence.

    Steps:
        1. Validate source
        2. Calculate original SHA-256
        3. Create evidence directory
        4. Copy original evidence
        5. Calculate copy SHA-256
        6. Verify hashes
        7. Create metadata
        8. Create chain-of-custody record
    """

    input_file = Path(input_file)

    if not input_file.exists():
        raise FileNotFoundError(
            f"Evidence file does not exist: {input_file}"
        )

    if not input_file.is_file():
        raise ValueError(
            f"Evidence source is not a file: {input_file}"
        )

    acquisition_time = utc_timestamp()

    evidence_id = (
        f"EVD-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    )

    case_directory = (
        Path("repository/cases") / case_id / evidence_id
    )

    evidence_directory = case_directory / "evidence"
    evidence_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    original_hash = calculate_sha256(input_file)

    destination = evidence_directory / input_file.name

    shutil.copy2(input_file, destination)

    copied_hash = calculate_sha256(destination)

    integrity_verified = (
        original_hash == copied_hash
    )

    metadata = {
        "case_id": case_id,
        "evidence_id": evidence_id,
        "source": str(input_file.absolute()),
        "acquired_file": str(destination.absolute()),
        "filename": input_file.name,
        "file_size_bytes": input_file.stat().st_size,
        "hash_algorithm": "SHA-256",
        "original_hash": original_hash,
        "forensic_copy_hash": copied_hash,
        "integrity_verified": integrity_verified,
        "acquisition_timestamp_utc": acquisition_time,
        "operator": operator
    }

    metadata_file = case_directory / "metadata.json"

    with open(metadata_file, "w") as f:
        json.dump(
            metadata,
            f,
            indent=4
        )

    chain_of_custody = [
        {
            "event_id": 1,
            "event": "EVIDENCE_ACQUIRED",
            "timestamp_utc": acquisition_time,
            "operator": operator,
            "evidence_id": evidence_id,
            "description": "Digital evidence acquired."
        },
        {
            "event_id": 2,
            "event": "HASH_CALCULATED",
            "timestamp_utc": acquisition_time,
            "operator": operator,
            "evidence_id": evidence_id,
            "algorithm": "SHA-256",
            "hash": original_hash
        },
        {
            "event_id": 3,
            "event": "FORENSIC_COPY_CREATED",
            "timestamp_utc": acquisition_time,
            "operator": operator,
            "evidence_id": evidence_id,
            "copy": str(destination.absolute())
        },
        {
            "event_id": 4,
            "event": "INTEGRITY_VERIFIED",
            "timestamp_utc": acquisition_time,
            "operator": operator,
            "evidence_id": evidence_id,
            "original_hash": original_hash,
            "copy_hash": copied_hash,
            "verified": integrity_verified
        }
    ]

    custody_file = (
        case_directory / "chain_of_custody.json"
    )

    with open(custody_file, "w") as f:
        json.dump(
            chain_of_custody,
            f,
            indent=4
        )

    print("=" * 60)
    print("DRONE FORENSICS TOOLKIT")
    print("EVIDENCE ACQUISITION")
    print("=" * 60)

    print(f"\nCase ID       : {case_id}")
    print(f"Evidence ID   : {evidence_id}")
    print(f"Source        : {input_file}")
    print(f"Evidence copy : {destination}")

    print("\nSHA-256")
    print("-" * 60)
    print(f"Original      : {original_hash}")
    print(f"Forensic copy : {copied_hash}")

    print("\nIntegrity")
    print("-" * 60)

    if integrity_verified:
        print("STATUS        : VERIFIED")
    else:
        print("STATUS        : FAILED")

    print("\nMetadata      :", metadata_file)
    print("Chain custody:", custody_file)

    print("=" * 60)

    return metadata


def main():
    parser = argparse.ArgumentParser(
        description="Drone Forensics Evidence Acquisition Tool"
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to evidence file"
    )

    parser.add_argument(
        "--case",
        required=True,
        help="Forensic case ID"
    )

    parser.add_argument(
        "--operator",
        default="drone_forensics",
        help="Operator identifier"
    )

    args = parser.parse_args()

    acquire_evidence(
        input_file=args.input,
        case_id=args.case,
        operator=args.operator
    )


if __name__ == "__main__":
    main()

