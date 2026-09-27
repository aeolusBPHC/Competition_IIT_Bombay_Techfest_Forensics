"""
Vendor-neutral normalization of image/video metadata.

Every normalized value is stored together with the exact tag it came from
(e.g. "XMP:{http://www.dji.com/drone-dji/1.0/}RelativeAltitude"), so an
examiner can always trace a number back to the file. Nothing is derived
from vendor names: fields are matched by standard EXIF tags first, then by
XMP local names from an alias table. Adding a new vendor spelling means
adding one alias, not new code.

Consistency checks compare independent sources inside the same file (EXIF
vs XMP position, camera clock vs GPS clock, EXIF vs XMP make). They report
observations, not conclusions: a disagreement can come from editing, from
a wrong camera clock, or from the device itself.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from media.xmp import XmpProperty, by_local_name

# normalized field -> XMP local names (lower-case), in priority order
XMP_ALIASES: dict[str, list[str]] = {
    "latitude": ["gpslatitude", "latitude"],
    "longitude": ["gpslongitude", "gpslongtitude", "longitude", "longtitude"],
    "absolute_altitude_m": ["absolutealtitude", "altitudeamsl"],
    "relative_altitude_m": ["relativealtitude", "height"],
    "aircraft_yaw_deg": ["flightyawdegree", "heading"],
    "aircraft_pitch_deg": ["flightpitchdegree", "pitchangle"],
    "aircraft_roll_deg": ["flightrolldegree", "rollangle"],
    "camera_yaw_deg": ["gimbalyawdegree", "yaw"],
    "camera_pitch_deg": ["gimbalpitchdegree", "pitch"],
    "camera_roll_deg": ["gimbalrolldegree", "roll"],
    "ground_speed_m_s": ["groundspeed"],
    "air_speed_m_s": ["airspeed"],
    "velocity_x_m_s": ["flightxspeed"],
    "velocity_y_m_s": ["flightyspeed"],
    "velocity_z_m_s": ["flightzspeed"],
    "gps_utc_time": ["utctime"],
    "firmware_version": ["firmwareversion"],
    "make": ["make"],
    "model": ["model"],
}
SERIAL_ALIASES = ["serialnumber", "droneserialnumber", "aircraftserialnumber", "camerasn",
                  "camserialnumber", "autopilotsn", "framesn", "bodyserialnumber"]
DRONE_FIELDS = {"relative_altitude_m", "aircraft_yaw_deg", "aircraft_pitch_deg", "aircraft_roll_deg",
                "camera_yaw_deg", "camera_pitch_deg", "velocity_x_m_s", "ground_speed_m_s", "air_speed_m_s"}
TEXT_FIELDS = {"gps_utc_time", "firmware_version", "make", "model"}

GPS_DISAGREEMENT_M = 50.0


def _num(value: Any) -> float | None:
    if isinstance(value, list):
        return None
    try:
        v = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _set(fields: dict, name: str, value: Any, source: str) -> None:
    if value is not None and name not in fields:
        fields[name] = {"value": value, "source": source}


def _xmp_source(p: XmpProperty) -> str:
    return f"XMP:{p.qualified}"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * 6371000.0 * math.asin(math.sqrt(a))


def normalize(exif: dict[str, Any] | None, xmp_props: list[XmpProperty],
              video: dict[str, Any] | None = None) -> dict[str, Any]:
    fields: dict[str, dict[str, Any]] = {}
    serials: dict[str, str] = {}
    flags: list[dict[str, Any]] = []

    # ---- 1. standard EXIF (highest priority)
    tags = (exif or {}).get("tags", {})
    gps = (exif or {}).get("gps", {})
    _set(fields, "make", tags.get("Make"), "EXIF:Make")
    _set(fields, "model", tags.get("Model"), "EXIF:Model")
    _set(fields, "software", tags.get("Software"), "EXIF:Software")
    _set(fields, "latitude", gps.get("latitude"), "EXIF:GPSLatitude")
    _set(fields, "longitude", gps.get("longitude"), "EXIF:GPSLongitude")
    _set(fields, "gps_altitude_m", gps.get("altitude_m"), "EXIF:GPSAltitude")
    _set(fields, "gps_utc_time", gps.get("utc_datetime"), "EXIF:GPSDateStamp+GPSTimeStamp")
    _set(fields, "image_direction_deg", gps.get("image_direction_deg"), "EXIF:GPSImgDirection")
    original = tags.get("DateTimeOriginal")
    if original:
        sub = tags.get("SubSecTimeOriginal")
        _set(fields, "capture_time_camera_clock", f"{original}.{sub}" if sub else original,
             "EXIF:DateTimeOriginal")
    _set(fields, "capture_time_utc_offset", tags.get("OffsetTimeOriginal"), "EXIF:OffsetTimeOriginal")
    for tag in ("BodySerialNumber", "CameraSerialNumber", "LensSerialNumber"):
        if tags.get(tag):
            serials[f"EXIF:{tag}"] = str(tags[tag])

    # ---- 2. video container
    if video:
        _set(fields, "make", video.get("strings", {}).get("make"), "QuickTime:\u00a9mak")
        _set(fields, "model", video.get("strings", {}).get("model"), "QuickTime:\u00a9mod")
        _set(fields, "capture_time_utc", video.get("creation_time_utc"), "QuickTime:mvhd.creation_time")
        _set(fields, "duration_s", video.get("duration_s"), "QuickTime:mvhd.duration")
        loc = video.get("location") or {}
        _set(fields, "latitude", loc.get("latitude"), "QuickTime:ISO6709")
        _set(fields, "longitude", loc.get("longitude"), "QuickTime:ISO6709")
        _set(fields, "gps_altitude_m", loc.get("altitude_m"), "QuickTime:ISO6709")

    # ---- 3. XMP by local name (fills gaps; also kept separately for cross-checks)
    index = by_local_name(xmp_props)
    xmp_position: dict[str, tuple[float, str]] = {}
    for name, aliases in XMP_ALIASES.items():
        for alias in aliases:
            for p in index.get(alias, []):
                value = p.value if name in TEXT_FIELDS else _num(p.value)
                if value in (None, ""):
                    continue
                if name in ("latitude", "longitude"):
                    xmp_position.setdefault(name, (value, _xmp_source(p)))
                _set(fields, name, value, _xmp_source(p))
                break
            if name in fields and fields[name]["source"].startswith("XMP"):
                break
    for alias in SERIAL_ALIASES:
        for p in index.get(alias, []):
            if isinstance(p.value, str) and p.value:
                serials[_xmp_source(p)] = p.value

    # ---- 4. consistency checks (observations only)
    if gps.get("latitude") is not None and {"latitude", "longitude"} <= xmp_position.keys():
        (xlat, xsrc), (xlon, _) = xmp_position["latitude"], xmp_position["longitude"]
        dist = haversine_m(gps["latitude"], gps["longitude"], xlat, xlon)
        if dist > GPS_DISAGREEMENT_M:
            flags.append({"flag": "EXIF_XMP_POSITION_DISAGREE", "distance_m": round(dist, 1),
                          "note": "EXIF GPS and XMP position differ by more than "
                                  f"{GPS_DISAGREEMENT_M:.0f} m"})
    exif_make = tags.get("Make")
    xmp_make = next((p.value for p in index.get("make", []) if isinstance(p.value, str)), None)
    if exif_make and xmp_make and exif_make.lower() != xmp_make.lower():
        flags.append({"flag": "EXIF_XMP_MAKE_DISAGREE", "exif": exif_make, "xmp": xmp_make})
    offset = _clock_offset(tags.get("DateTimeOriginal"), gps.get("utc_datetime"))
    if offset is not None:
        fields["camera_clock_minus_gps_utc_s"] = {"value": offset,
                                                  "source": "derived: EXIF:DateTimeOriginal - GPS UTC"}
        remainder = abs(offset) % 900
        drift = min(remainder, 900 - remainder)
        if drift > 60 or abs(offset) > 14 * 3600:
            flags.append({"flag": "CAMERA_CLOCK_IRREGULAR_OFFSET", "offset_s": offset,
                          "note": "camera clock differs from GPS UTC by more than a whole time-zone "
                                  "offset (+-60 s); the camera clock may be wrong or edited"})

    has_drone = any(k in fields for k in DRONE_FIELDS)
    vocab = sorted({p.namespace for alias in [a for v in XMP_ALIASES.values() for a in v] + SERIAL_ALIASES
                    for p in index.get(alias, []) if p.namespace})
    return {"fields": fields, "serial_numbers": serials, "flags": flags,
            "drone_telemetry_present": has_drone, "telemetry_namespaces": vocab}


def _clock_offset(local: str | None, utc: str | None) -> float | None:
    if not local or not utc:
        return None
    try:
        loc = datetime.strptime(local[:19], "%Y:%m:%d %H:%M:%S")
        gps = datetime.strptime(utc[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    return round((loc - gps).total_seconds(), 3)
