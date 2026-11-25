"""Small defensive decoder for common GoPro GPMF scalar/vector telemetry."""

from __future__ import annotations

import math
import struct
from typing import Any, Iterator


class GPMFError(ValueError):
    pass


def _records(payload: bytes) -> Iterator[dict[str, Any]]:
    offset = 0
    while offset < len(payload):
        if payload[offset:].strip(b"\x00") == b"":
            return
        if offset + 8 > len(payload):
            raise GPMFError(f"truncated KLV header at byte {offset}")
        key_bytes = payload[offset:offset + 4]
        try:
            key = key_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            raise GPMFError(f"invalid KLV key at byte {offset}") from exc
        kind = chr(payload[offset + 4])
        size = payload[offset + 5]
        repeat = int.from_bytes(payload[offset + 6:offset + 8], "big")
        length = size * repeat
        start = offset + 8
        end = start + length
        if end > len(payload):
            raise GPMFError(f"{key} payload extends beyond its containing record")
        yield {"key": key, "type": kind, "size": size, "repeat": repeat,
               "data": payload[start:end]}
        offset = (end + 3) & ~3


_STRUCTS = {
    "b": (1, ">b"), "B": (1, ">B"), "s": (2, ">h"), "S": (2, ">H"),
    "l": (4, ">i"), "L": (4, ">I"), "f": (4, ">f"), "d": (8, ">d"),
    "j": (8, ">q"), "J": (8, ">Q"),
}


def _values(record: dict[str, Any]) -> list[Any] | str | None:
    kind, size, data = record["type"], record["size"], record["data"]
    if kind in ("c", "U"):
        return data.decode("latin-1", "replace").rstrip("\x00 ")
    spec = _STRUCTS.get(kind)
    if not spec or size % spec[0]:
        return None
    width, fmt = spec
    count = len(data) // width
    result = [struct.unpack_from(fmt, data, i * width)[0] for i in range(count)]
    if any(isinstance(v, float) and not math.isfinite(v) for v in result):
        return None
    return result


def _nested(record: dict[str, Any]) -> list[dict[str, Any]]:
    if record["type"] != "\x00":
        return []
    return list(_records(record["data"]))


def _first(records: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    return next((record for record in records if record["key"] == key), None)


def _stream(record: dict[str, Any], payload_index: int, track_index: int) -> dict[str, Any] | None:
    entries = _nested(record)
    result: dict[str, Any] = {"payload_index": payload_index, "track_index": track_index,
                              "stream": None, "payload_bytes": record["repeat"],
                              "values": None, "units": None, "scale": None}
    name = _first(entries, "STNM")
    result["stream_name"] = _values(name) if name else None
    clock = _first(entries, "TICK")
    result["source_clock_ticks"] = (_values(clock) or [None])[0] if clock else None
    total = _first(entries, "TSMP")
    result["total_samples"] = (_values(total) or [None])[0] if total else None
    unit = _first(entries, "SIUN") or _first(entries, "UNIT")
    unit_value = _values(unit) if unit else None
    result["units"] = unit_value
    fix = _first(entries, "GPSF")
    precision = _first(entries, "GPSP")
    if fix or precision:
        result["gps_quality"] = {
            "fix": (_values(fix) or [None])[0] if fix else None,
            "precision_raw": (_values(precision) or [None])[0] if precision else None,
            "precision_units": "source-specific GPMF GPSP scale; interpretation not inferred",
        }
    scale_rec = _first(entries, "SCAL")
    scales = _values(scale_rec) if scale_rec else None
    if isinstance(scales, list):
        result["scale"] = scales
    keys = {entry["key"] for entry in entries}
    supported = next((key for key in ("ACCL", "GYRO", "GPS5", "GPS9", "GPSU") if key in keys), None)
    if supported is None:
        return None
    record_data = _first(entries, supported)
    values = _values(record_data) if record_data else None
    result["stream"] = supported
    if supported in {"ACCL", "GYRO"} and isinstance(values, list):
        width = max(1, record_data["size"] // (_STRUCTS.get(record_data["type"], (1, ""))[0]))
        if width in (3, 4) and len(values) % width == 0:
            vectors = [values[i:i + width] for i in range(0, len(values), width)]
            factors = scales if isinstance(scales, list) and len(scales) > 1 else (scales * width if scales else None)
            if factors:
                vectors = [[component / factors[axis] if factors[axis] else None
                            for axis, component in enumerate(vector)] for vector in vectors]
            result["values"] = vectors
            result["axis_order"] = ["z", "x", "y"] if width == 3 else ["z", "x", "y", "w"]
        else:
            result["values"] = values
            result["warning"] = "sensor vector payload did not have a recognized 3/4-axis shape"
    elif supported in {"GPS5", "GPS9"} and isinstance(values, list):
        width = record_data["size"] // 4
        scales_list = scales if isinstance(scales, list) else []
        result["values"] = [
            [v / scales_list[i % width] if i < len(scales_list) and scales_list[i] else v
             for i, v in enumerate(values[start:start + width])]
            for start in range(0, len(values), width)
        ]
        result["axis_order"] = ["latitude_deg", "longitude_deg", "altitude_unknown_datum_m",
                                 "speed_2d_m_s", "speed_3d_m_s"] if supported == "GPS5" else None
        if supported == "GPS5":
            result["units_by_axis"] = ["degrees", "degrees", "m; altitude datum unknown",
                                       "m/s", "m/s"]
            # SIUN stores several fixed-width labels here; preserve the source
            # bytes without presenting their concatenated display as one unit.
            result["source_units"] = unit_value
            result["units"] = None
    elif supported == "GPSU":
        result["values"] = values
    if isinstance(values, list):
        result["decoded_sample_count"] = len(result.get("values") or [])
    return result


def decode(payload: bytes, track_index: int) -> dict[str, Any]:
    """Decode ACCL, GYRO, GPS5/9 and GPSU streams from an extracted gpmd track."""
    packets = []
    warnings = []
    for packet_index, device in enumerate(_records(payload)):
        if device["key"] != "DEVC" or device["type"] != "\x00":
            continue
        streams = []
        try:
            for stream in _nested(device):
                if stream["key"] == "STRM" and stream["type"] == "\x00":
                    parsed = _stream(stream, packet_index, track_index)
                    if parsed:
                        streams.append(parsed)
        except GPMFError as exc:
            warnings.append(f"GPMF packet {packet_index}: {exc}")
            continue
        if streams:
            gps_time = next((stream.get("values") for stream in streams
                             if stream.get("stream") == "GPSU" and stream.get("values")), None)
            packets.append({
                "packet_index": packet_index,
                "timestamp": ({"value": gps_time, "basis": "utc", "source_tag": "GPMF:GPSU"}
                              if gps_time else None),
                "streams": streams,
                "limitations": [
                    "Sensor vectors are decoded in source axis order; they are not rotated into world/camera coordinates.",
                    "GPMF payload time and per-sample cadence are not converted to a common video or wall clock.",
                ],
            })
    return {"packets": packets, "warnings": warnings,
            "decoded_sensor_sample_count": sum(s.get("decoded_sample_count", 0)
                                                for p in packets for s in p["streams"])}
