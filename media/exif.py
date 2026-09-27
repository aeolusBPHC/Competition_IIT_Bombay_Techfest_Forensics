"""
Standard EXIF extraction (Pillow).

Only tags defined by the EXIF/TIFF standards are read, which is what makes
this vendor-neutral: GPS position, capture time, make/model and serial
numbers live in the same standard tags whichever manufacturer wrote them.
Vendor MakerNotes are NOT decoded (they are proprietary and, for DJI,
known to contain invalid pointers); their presence is only recorded.
"""

from __future__ import annotations

from typing import Any

try:
    from PIL import Image
except ImportError:  # pragma: no cover - reported by the extractor
    Image = None

IFD0_TAGS = {0x010F: "Make", 0x0110: "Model", 0x0131: "Software", 0x0132: "DateTime",
             0x013B: "Artist", 0xC62F: "CameraSerialNumber"}
EXIF_TAGS = {0x9003: "DateTimeOriginal", 0x9004: "DateTimeDigitized",
             0x9010: "OffsetTime", 0x9011: "OffsetTimeOriginal", 0x9291: "SubSecTimeOriginal",
             0xA420: "ImageUniqueID", 0xA430: "CameraOwnerName", 0xA431: "BodySerialNumber",
             0xA435: "LensSerialNumber", 0x927C: "MakerNote"}
GPS_TAGS = {1: "GPSLatitudeRef", 2: "GPSLatitude", 3: "GPSLongitudeRef", 4: "GPSLongitude",
            5: "GPSAltitudeRef", 6: "GPSAltitude", 7: "GPSTimeStamp", 12: "GPSSpeedRef",
            13: "GPSSpeed", 16: "GPSImgDirectionRef", 17: "GPSImgDirection",
            18: "GPSMapDatum", 29: "GPSDateStamp"}


def _clean(value: Any) -> Any:
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    if isinstance(value, str):
        return value.replace("\x00", "").strip() or None
    if isinstance(value, tuple):
        return tuple(_clean(v) for v in value)
    try:
        return float(value) if hasattr(value, "numerator") and not isinstance(value, int) else value
    except (TypeError, ZeroDivisionError, ValueError):
        return None


def _dms_to_degrees(dms: Any, ref: str | None) -> float | None:
    try:
        d, m, s = (float(x) for x in dms)
    except (TypeError, ValueError):
        return None
    if any(v != v for v in (d, m, s)):  # NaN from 0/0 rationals
        return None
    value = d + m / 60.0 + s / 3600.0
    return -value if ref in ("S", "W") else value


def read(path: str) -> dict[str, Any]:
    """Return {'tags': {...}, 'gps': {...}, 'errors': [...]} for one image."""
    result: dict[str, Any] = {"tags": {}, "gps": {}, "errors": []}
    if Image is None:
        result["errors"].append("Pillow not installed; EXIF not read")
        return result
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            result["pixel_size"] = list(img.size)
            for tag, name in IFD0_TAGS.items():
                if tag in exif:
                    result["tags"][name] = _clean(exif[tag])
            sub = exif.get_ifd(0x8769)
            for tag, name in EXIF_TAGS.items():
                if tag in sub:
                    if name == "MakerNote":
                        result["tags"]["MakerNotePresent"] = True
                    else:
                        result["tags"][name] = _clean(sub[tag])
            gps = exif.get_ifd(0x8825)
            raw_gps = {name: _clean(gps[tag]) for tag, name in GPS_TAGS.items() if tag in gps}
            result["gps_raw"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in raw_gps.items()}
            result["gps"] = _interpret_gps(raw_gps)
    except Exception as exc:  # corrupt or unsupported image: record, never crash
        result["errors"].append(f"EXIF read failed: {type(exc).__name__}: {exc}")
    return result


def _interpret_gps(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    lat = _dms_to_degrees(raw.get("GPSLatitude"), raw.get("GPSLatitudeRef"))
    lon = _dms_to_degrees(raw.get("GPSLongitude"), raw.get("GPSLongitudeRef"))
    # 0/0 coordinates are what many cameras write when they have no fix.
    if lat is not None and lon is not None and not (lat == 0 and lon == 0):
        out["latitude"], out["longitude"] = lat, lon
    alt = raw.get("GPSAltitude")
    if isinstance(alt, (int, float)) and alt == alt:
        ref = raw.get("GPSAltitudeRef")
        below = ref in (1, b"\x01", "\x01")
        out["altitude_m"] = -alt if below else alt
    date, time_ = raw.get("GPSDateStamp"), raw.get("GPSTimeStamp")
    if date and time_:
        try:
            h, m, s = (float(x) for x in time_)
            out["utc_datetime"] = f"{date.replace(':', '-')}T{int(h):02d}:{int(m):02d}:{s:06.3f}Z"
        except (TypeError, ValueError):
            pass
    if isinstance(raw.get("GPSImgDirection"), float):
        out["image_direction_deg"] = raw["GPSImgDirection"]
    return out
