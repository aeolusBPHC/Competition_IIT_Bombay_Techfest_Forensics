from dataclasses import asdict, is_dataclass
from typing import Any


def serialize_evidence(value: Any) -> Any:
    """
    Convert normalized forensic records into JSON-safe dictionaries.

    This function intentionally knows nothing about PX4, ArduPilot,
    Betaflight, INAV, or MAVLink.
    """

    if value is None:
        return None

    if is_dataclass(value):
        return {
            key: serialize_evidence(val)
            for key, val in asdict(value).items()
        }

    if isinstance(value, dict):
        return {
            str(key): serialize_evidence(val)
            for key, val in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            serialize_evidence(item)
            for item in value
        ]

    if isinstance(value, set):
        return [
            serialize_evidence(item)
            for item in sorted(value, key=str)
        ]

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)
