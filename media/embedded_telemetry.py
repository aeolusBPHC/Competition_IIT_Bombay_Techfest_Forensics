"""Extract embedded camera/drone telemetry with ExifTool and ffprobe.

The MP4 track indexes are inspected with ffprobe. ExifTool decodes the
format-specific payloads (GoPro GPMF and DJI's model-specific djmd protobufs),
so this module can retain original tag names and values without guessing at
unknown schema fields.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from functools import lru_cache
from typing import Any

from media import gpmf

SCHEMA_VERSION = "1.0"
MAX_JSON_BYTES = 512 * 1024 * 1024
MAX_GPMF_BYTES = 256 * 1024 * 1024
DJI_FORMATS = {"DJI_djmd", "DJI_dbgi"}
_DOC_GROUP = re.compile(r"^doc\d+(?:-|$)", re.IGNORECASE)
_DJI_SCHEMA = re.compile(r"dvtm_[a-z0-9_]+", re.IGNORECASE)


def _run(command: list[str], timeout_s: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout_s,
                          check=False)


@lru_cache(maxsize=4)
def _exiftool_version(executable: str) -> tuple[int, ...] | None:
    try:
        proc = _run([executable, "-ver"], 10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    match = re.search(r"\d+(?:\.\d+)+", proc.stdout)
    return tuple(int(part) for part in match.group(0).split(".")) if match else None


def _version_text(version: tuple[int, ...] | None) -> str | None:
    return ".".join(str(part) for part in version) if version else None


def _track_inventory(path: str, ffprobe: str, timeout_s: int) -> tuple[list[dict], list[str]]:
    command = [ffprobe, "-v", "error", "-show_streams", "-of", "json", path]
    try:
        proc = _run(command, timeout_s)
    except subprocess.TimeoutExpired:
        return [], [f"ffprobe timed out after {timeout_s} seconds while listing streams"]
    except OSError as exc:
        return [], [f"could not run ffprobe: {type(exc).__name__}: {exc}"]
    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()
        return [], ["ffprobe could not list streams" + (f": {detail[-1][:300]}" if detail else "")]
    try:
        streams = json.loads(proc.stdout).get("streams", [])
    except (TypeError, json.JSONDecodeError) as exc:
        return [], [f"ffprobe returned invalid stream JSON: {exc}"]
    inventory = []
    for stream in streams:
        tag = str(stream.get("codec_tag_string", "")).strip().lower()
        if tag not in {"gpmd", "djmd", "dbgi"}:
            continue
        inventory.append({
            "index": stream.get("index"),
            "codec_type": stream.get("codec_type"),
            "codec_tag": tag,
            "codec_name": stream.get("codec_name"),
            "handler_name": (stream.get("tags") or {}).get("handler_name"),
            "format": {"gpmd": "GoPro_GPMF", "djmd": "DJI_djmd",
                       "dbgi": "DJI_dbgi"}[tag],
        })
    return inventory, []


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}:{key}" if prefix else str(key)
            result.update(_flatten(child, name))
    else:
        result[prefix] = value
    return result


def _leaf(tag: str) -> str:
    return tag.rsplit(":", 1)[-1].strip().lower().replace("_", "")


def _matches(tags: dict[str, Any], names: set[str]) -> tuple[str, Any] | tuple[None, None]:
    for tag, value in tags.items():
        if _leaf(tag) in names and value not in (None, ""):
            return tag, value
    return None, None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or isinstance(value, (list, dict, tuple)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _timestamp(tags: dict[str, Any]) -> dict[str, Any] | None:
    tag, value = _matches(tags, {"gpsdatetime", "datetimeutc", "datetime", "gpsu"})
    if tag is None:
        tag, value = _matches(tags, {"timestamp", "sampletime", "timeoffset"})
        if tag is None:
            return None
        return {"value": value, "basis": "source_clock_uninterpreted", "source_tag": tag}

    text = str(value).strip()
    # Keep a timestamp as UTC only when its source explicitly states a zone.
    if text.endswith(("Z", "z")) or re.search(r"[+-]\d{2}:?\d{2}$", text):
        return {"value": value, "basis": "utc", "source_tag": tag}
    return {"value": value, "basis": "timezone_unspecified", "source_tag": tag}


def _vector(tags: dict[str, Any], aliases: set[str], axis_aliases: tuple[set[str], ...],
            units: str | None) -> dict[str, Any] | None:
    tag, value = _matches(tags, aliases)
    if tag is not None:
        return {"value": value, "units": units, "source_tag": tag}
    axes = []
    source_tags = []
    for aliases_for_axis in axis_aliases:
        axis_tag, axis_value = _matches(tags, aliases_for_axis)
        if axis_tag is None:
            axes.append(None)
        else:
            axes.append(_number(axis_value))
            source_tags.append(axis_tag)
    if any(v is not None for v in axes):
        return {"value": axes, "axis_order": ["x", "y", "z"], "units": units,
                "source_tags": source_tags}
    return None


def _sample(record: dict[str, Any], track_format: str) -> dict[str, Any] | None:
    tags = _flatten(record)
    has_doc_group = any(_DOC_GROUP.match(part) for key in tags for part in key.split(":"))
    leaves = {_leaf(key) for key in tags}
    if track_format in DJI_FORMATS:
        # `-ee3` puts these packets in Doc groups; dvtm names are model schemas.
        specific = any(_DJI_SCHEMA.search(key) for key in tags) or (
            has_doc_group and any("dji" in key.lower() for key in tags)
        )
    else:
        specific = has_doc_group and bool(leaves & {
            "gps5", "gps9", "gpsu", "gpslatitude", "gpslongitude", "gpsaltitude",
            "gpsdatetime", "accl", "gyro", "accelerometer", "gyroscope", "attitude",
            "attitudetarget", "cameraorientation", "imageorientation", "gravityvector",
            "gopro",
        })
    if not specific:
        return None

    lat_tag, lat_raw = _matches(tags, {"gpslatitude", "latitude"})
    lon_tag, lon_raw = _matches(tags, {"gpslongitude", "gpslongtitude", "longitude"})
    lat, lon = _number(lat_raw), _number(lon_raw)
    gps = None
    if lat is not None or lon is not None:
        gps = {"latitude": lat, "longitude": lon, "source_tags": {
            "latitude": lat_tag, "longitude": lon_tag,
        }, "coordinate_reference": "WGS84 (GPS-tag convention; datum not independently verified)"}
        if lat is not None and not -90 <= lat <= 90:
            gps["warning"] = "latitude is outside the valid range"
        if lon is not None and not -180 <= lon <= 180:
            gps["warning"] = "longitude is outside the valid range"

    altitude_fields = {}
    for normalized, aliases in (
        ("absolute_m", {"gpsaltitude", "absolutealtitude"}),
        ("relative_m", {"relativealtitude", "relaltitude"}),
        ("unspecified_reference", {"altitude"}),
    ):
        tag, value = _matches(tags, aliases)
        numeric = _number(value)
        if tag is not None:
            altitude_fields[normalized] = {
                "value": numeric if numeric is not None else value,
                "units": "m" if numeric is not None and track_format == "GoPro_GPMF" else None,
                "reference": "unknown; source tag does not establish MSL, ellipsoid, or takeoff-relative datum",
                "source_tag": tag,
            }

    gps_quality = {}
    for normalized, aliases in (
        ("fix_type", {"gpsfix", "gpsfixtype", "fix", "fixtype"}),
        ("satellites", {"gpsnumsat", "numsatellites", "satellites"}),
        ("hdop", {"hdop", "gpshdop"}),
        ("vdop", {"vdop", "gpsvdop"}),
        ("horizontal_accuracy", {"gpsaccuracy", "gpshorizontalaccuracy", "horizontalaccuracy", "hacc"}),
        ("vertical_accuracy", {"gpsverticalaccuracy", "verticalaccuracy", "vacc"}),
    ):
        tag, value = _matches(tags, aliases)
        if tag is not None:
            gps_quality[normalized] = {"value": _number(value) if _number(value) is not None else value,
                                       "units": None, "source_tag": tag}
    if gps is not None and gps_quality:
        gps["quality"] = gps_quality

    speed_tag, speed_value = _matches(tags, {"gpsspeed", "speed", "groundspeed", "velocity"})
    gps_speed = ({"value": _number(speed_value) if _number(speed_value) is not None else speed_value,
                  "units": None, "source_tag": speed_tag} if speed_tag else None)

    attitude: dict[str, Any] = {}
    for role, aliases_by_axis in (
        ("aircraft", (
            {"droneroll", "flightroll", "flightrolldegree", "aircraftroll"},
            {"dronepitch", "flightpitch", "flightpitchdegree", "aircraftpitch"},
            {"droneyaw", "flightyaw", "flightyawdegree", "aircraftyaw"},
        )),
        ("gimbal", (
            {"gimbalroll", "gimbalrolldegree", "cameraroll"},
            {"gimbalpitch", "gimbalpitchdegree", "camerapitch"},
            {"gimbalyaw", "gimbalyawdegree", "camerayaw"},
        )),
    ):
        axes = []
        source_tags = []
        for aliases in aliases_by_axis:
            tag, value = _matches(tags, aliases)
            axes.append(_number(value))
            if tag:
                source_tags.append(tag)
        if any(axis is not None for axis in axes):
            units = "degrees" if any("degree" in tag.lower() for tag in source_tags) else None
            attitude[role] = {"roll_pitch_yaw": axes, "axis_order": ["roll", "pitch", "yaw"],
                              "units": units, "source_tags": source_tags}

    accelerometer = _vector(
        tags, {"accelerometer", "accl"},
        ({"accelerometerx"}, {"accelerometery"}, {"accelerometerz"}),
        "m/s^2" if track_format == "GoPro_GPMF" else None,
    )
    gyroscope = _vector(
        tags, {"gyroscope", "gyro"},
        ({"gyroscopex"}, {"gyroscopey"}, {"gyroscopez"}),
        "rad/s" if track_format == "GoPro_GPMF" else None,
    )
    motion = attitude.copy()
    if accelerometer:
        motion["accelerometer"] = accelerometer
    if gyroscope:
        motion["gyroscope"] = gyroscope

    camera_settings = {}
    for normalized, aliases in (
        ("iso", {"iso", "isospeed"}),
        ("shutter_time", {"shutterspeed", "exposuretime", "shutter"}),
        ("exposure_compensation", {"exposurecompensation", "exposurebias"}),
    ):
        tag, value = _matches(tags, aliases)
        if tag is not None:
            camera_settings[normalized] = {"value": _number(value) if _number(value) is not None else value,
                                            "units": None, "source_tag": tag}

    timestamp = _timestamp(tags)
    meaningful = gps is not None or bool(altitude_fields) or bool(motion) or timestamp is not None or bool(camera_settings) or gps_speed is not None
    if not meaningful:
        return None
    return {
        "index": None,
        "source_format": track_format,
        "timestamp": timestamp,
        "gps": gps,
        "altitude": altitude_fields or None,
        "camera_motion": motion or None,
        "speed": gps_speed,
        "camera_settings": camera_settings or None,
        "raw_tags": tags,
        "limitations": [
            "Sample timing is kept in the source clock; no video-time or UTC alignment is inferred.",
            "Axis orientation is not transformed; values retain the decoded source coordinate frame.",
            "GPS datum is labelled by GPS-tag convention but is not independently verified; altitude datum and unspecified units remain unknown.",
        ],
    }


def read(path: str, *, ffprobe: str | None = None, exiftool: str | None = None,
         timeout_s: int = 900) -> dict[str, Any]:
    """Read telemetry in embedded `gpmd` and DJI `djmd` MP4/MOV tracks.

    Format payload parsing is delegated to ExifTool, whose device-specific DJI
    protobuf schemas are maintained outside this project. Unknown tags remain
    in `raw_tags`; no coordinate frame or wall-clock mapping is fabricated.
    """
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "unavailable",
        "formats": [],
        "tracks": [],
        "sample_count": 0,
        "samples": [],
        "gpmf": None,
        "warnings": [],
    }
    ffprobe_path = ffprobe or shutil.which("ffprobe")
    if not ffprobe_path:
        result["warnings"].append("ffprobe is not installed; embedded track formats cannot be identified")
        return result
    tracks, warnings = _track_inventory(path, ffprobe_path, timeout_s)
    result["warnings"].extend(warnings)
    result["tracks"] = tracks
    formats = sorted({track["format"] for track in tracks})
    result["formats"] = formats
    if not formats:
        result["status"] = "no_embedded_telemetry_track" if not warnings else "error"
        return result

    gpmf_tracks = [track for track in tracks if track["format"] == "GoPro_GPMF"]
    if gpmf_tracks:
        result["gpmf"] = _read_gpmf(path, gpmf_tracks, timeout_s)
        result["warnings"].extend(result["gpmf"].get("warnings", []))

    exiftool_path = exiftool or shutil.which("exiftool")
    if not exiftool_path:
        raw_count = (result.get("gpmf") or {}).get("decoded_sensor_sample_count", 0)
        result["status"] = "ok" if raw_count else "unavailable"
        result["warnings"].append("ExifTool is not installed; DJI telemetry and non-GPMF metadata were not decoded")
        return result
    version = _exiftool_version(exiftool_path)
    result["extractor"] = {"name": "ExifTool", "version": _version_text(version)}
    if set(formats) & DJI_FORMATS and (version is None or version < (13, 5)):
        result["warnings"].append(
            "this ExifTool version may not decode DJI djmd protobuf tracks; DJI djmd support "
            "requires ExifTool 13.05 or newer, and newer camera models may require later versions"
        )

    command = [exiftool_path, "-ee3", "-G3:4:5", "-n", "-json", path]
    try:
        proc = _run(command, timeout_s)
    except subprocess.TimeoutExpired:
        result["status"] = "error"
        result["warnings"].append(f"ExifTool timed out after {timeout_s} seconds")
        return result
    except OSError as exc:
        result["status"] = "error"
        result["warnings"].append(f"could not run ExifTool: {type(exc).__name__}: {exc}")
        return result
    if proc.returncode != 0:
        result["status"] = "error"
        detail = proc.stderr.strip().splitlines()
        result["warnings"].append("ExifTool failed" + (f": {detail[-1][:300]}" if detail else ""))
        return result
    if proc.stderr.strip():
        result["warnings"].extend(line[:300] for line in proc.stderr.splitlines() if line.strip())
    if len(proc.stdout.encode("utf-8", "replace")) > MAX_JSON_BYTES:
        result["status"] = "error"
        result["warnings"].append(f"ExifTool JSON exceeded the {MAX_JSON_BYTES} byte safety limit")
        return result
    try:
        records = json.loads(proc.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        result["status"] = "error"
        result["warnings"].append(f"ExifTool returned invalid JSON: {exc}")
        return result

    samples = []
    available_formats = set(formats)
    for record in records if isinstance(records, list) else []:
        flat = _flatten(record)
        leaves = {_leaf(key) for key in flat}
        has_doc_group = any(_DOC_GROUP.match(part) for key in flat for part in key.split(":"))
        has_dji_marker = any(_DJI_SCHEMA.search(key) or ":dji" in key.lower() for key in flat)
        has_gopro_marker = any("gopro" in key.lower() for key in flat) or bool(leaves & {
            "gps5", "gps9", "gpsu", "accl", "gyro", "accelerometer", "gyroscope",
        })
        candidates = []
        if (available_formats & DJI_FORMATS
                and (has_dji_marker or has_doc_group and len(available_formats) == 1)):
            candidates.append("DJI_dbgi" if "DJI_dbgi" in available_formats else "DJI_djmd")
        if "GoPro_GPMF" in available_formats and has_doc_group and has_gopro_marker:
            candidates.append("GoPro_GPMF")
        if not candidates and has_doc_group and len(available_formats) == 1:
            # With a single recognized embedded track, Doc packet groups are
            # unambiguous even when a parser version omits vendor group names.
            candidates.append(next(iter(available_formats)))
        if len(candidates) != 1:
            continue
        track_format = candidates[0]
        sample = _sample(record, track_format)
        if sample is not None:
            sample["index"] = len(samples)
            matching_tracks = [t for t in tracks if t["format"] == track_format]
            sample["track_indices"] = [t["index"] for t in matching_tracks]
            samples.append(sample)
    result["samples"] = samples
    result["sample_count"] = len(samples)
    if samples:
        result["status"] = "ok"
    else:
        result["status"] = "no_samples_decoded"
        raw_count = (result.get("gpmf") or {}).get("decoded_sensor_sample_count", 0)
        if raw_count:
            result["status"] = "ok"
            result["warnings"].append("ExifTool returned no normalized samples; decoded GPMF sensor data is available under gpmf")
        elif set(formats) & DJI_FORMATS and version is not None and version < (13, 5):
            result["warnings"].append("upgrade ExifTool; this version predates DJI djmd support")
        else:
            result["warnings"].append(
                "embedded telemetry tracks were detected, but no supported GPS, altitude, "
                "timestamp, or camera-motion samples were decoded"
            )
    return result


def _read_gpmf(path: str, tracks: list[dict[str, Any]], timeout_s: int) -> dict[str, Any]:
    """Use FFmpeg to demux gpmd packets, then decode supported GPMF values."""
    result: dict[str, Any] = {"status": "unavailable", "packets": [],
                              "decoded_sensor_sample_count": 0, "warnings": [],
                              "source": "GoPro GPMF KLV decoder"}
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        result["warnings"].append("ffmpeg is not installed; GPMF sensor payloads were not decoded")
        return result
    for track in tracks:
        index = track.get("index")
        try:
            proc = subprocess.run(
                [ffmpeg, "-v", "error", "-i", path, "-map", f"0:{index}",
                 "-c", "copy", "-f", "data", "pipe:1"],
                capture_output=True, timeout=timeout_s, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["warnings"].append(f"could not demux GPMF track {index}: {type(exc).__name__}")
            continue
        if proc.returncode:
            detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
            result["warnings"].append("ffmpeg could not demux GPMF track " + str(index)
                                      + (f": {detail[-1][:250]}" if detail else ""))
            continue
        if len(proc.stdout) > MAX_GPMF_BYTES:
            result["warnings"].append(f"GPMF track {index} exceeded {MAX_GPMF_BYTES} byte safety limit")
            continue
        try:
            decoded = gpmf.decode(proc.stdout, int(index))
        except (gpmf.GPMFError, TypeError, ValueError) as exc:
            result["warnings"].append(f"GPMF track {index} decode failed: {exc}")
            continue
        result["packets"].extend(decoded["packets"])
        result["decoded_sensor_sample_count"] += decoded["decoded_sensor_sample_count"]
        result["warnings"].extend(decoded["warnings"])
    result["status"] = "ok" if result["packets"] else "no_samples_decoded"
    if not result["packets"] and not result["warnings"]:
        result["warnings"].append("GPMF track was present, but no supported sensor samples were decoded")
    return result
