from pathlib import Path
import json

from acquisition.acquire import acquire_evidence, calculate_sha256


EMUFLIGHT_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "synthetic_emuflight.bbl"
)


def test_emuflight_acquisition_hash_integrity(tmp_path, monkeypatch):
    """
    Verify that EmuFlight Blackbox evidence receives the same
    SHA-256 acquisition and forensic-copy integrity treatment
    as other evidence formats.
    """

    source = EMUFLIGHT_FIXTURE.resolve()

    monkeypatch.chdir(tmp_path)

    metadata = acquire_evidence(
        input_file=source,
        case_id="CASE-EMUFLIGHT-TEST",
        operator="pytest",
    )

    assert metadata["hash_algorithm"] == "SHA-256"
    assert metadata["integrity_verified"] is True

    acquired_file = Path(metadata["acquired_file"])
    metadata_file = acquired_file.parent.parent / "metadata.json"
    custody_file = acquired_file.parent.parent / "chain_of_custody.json"

    assert acquired_file.exists()
    assert metadata_file.exists()
    assert custody_file.exists()

    expected_hash = calculate_sha256(source)
    copied_hash = calculate_sha256(acquired_file)

    assert metadata["original_hash"] == expected_hash
    assert metadata["forensic_copy_hash"] == expected_hash
    assert copied_hash == expected_hash

    saved_metadata = json.loads(
        metadata_file.read_text(encoding="utf-8")
    )

    assert saved_metadata["case_id"] == "CASE-EMUFLIGHT-TEST"
    assert saved_metadata["hash_algorithm"] == "SHA-256"
    assert saved_metadata["original_hash"] == expected_hash
    assert saved_metadata["forensic_copy_hash"] == expected_hash
    assert saved_metadata["integrity_verified"] is True

    custody = json.loads(
        custody_file.read_text(encoding="utf-8")
    )

    assert [event["event"] for event in custody] == [
        "EVIDENCE_ACQUIRED",
        "HASH_CALCULATED",
        "FORENSIC_COPY_CREATED",
        "INTEGRITY_VERIFIED",
    ]

    assert custody[1]["algorithm"] == "SHA-256"
    assert custody[1]["hash"] == expected_hash

    assert custody[3]["original_hash"] == expected_hash
    assert custody[3]["copy_hash"] == expected_hash
    assert custody[3]["verified"] is True
