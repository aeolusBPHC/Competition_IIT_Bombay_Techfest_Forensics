"""
Per-frame telemetry from .SRT subtitle sidecars written next to drone video.

Formats observed in real DJI samples (18 files, 2017-2022 models):

  keyed      [latitude: 41.42] [longitude: 2.16] [rel_alt: 1.2 abs_alt: 30.4]
             (older firmware spells it "longtitude")
  compact    GPS (-121.7458, 48.0771, 17), D 221.21m, H 200.70m, H.S .., F.PRY (..)
  legacy     HOME(149.0251,-20.2532) 2017.08.05 14:11:51
             GPS(149.0251,-20.2533,16) BAROMETER:1.9

The positional GPS(a, b, c) form does NOT have one axis order: a Mavic Pro
writes GPS(lon, lat, ..) while a Matrice 300 writes GPS(lat, lon, ..M).
The order is therefore resolved per file from the values themselves (a
coordinate beyond +-90 can only be a longitude). If the values cannot prove
the order, latitude/longitude are left None, the raw pair is kept, and the
file is flagged, unless the examiner supplies the order explicitly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_TIMECODE = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})")
_TAG = re.compile(r"<[^>]+>")
_BRACKET = re.compile(r"\[([^\]]*)\]")
_KEYVAL = re.compile(r"([A-Za-z_]+)\s*:\s*([^\s\]]+)")
_NUM = r"[-+]?\d+(?:\.\d+)?"
_GPS = re.compile(rf"\bGPS\s*\(\s*({_NUM})\s*,\s*({_NUM})\s*(?:,\s*({_NUM})\s*([Mm])?)?\s*\)")
_HOME = re.compile(rf"\bHOME\s*\(\s*({_NUM})\s*,\s*({_NUM})\s*(?:,\s*({_NUM})\s*m)?\s*\)")
_DIST = re.compile(rf"(?<![\w.])D\s+({_NUM})m")
_HEIGHT = re.compile(rf"(?<![\w.])H\s+({_NUM})m")
_HSPEED = re.compile(rf"H\.S\s+({_NUM})m/s")
_VSPEED = re.compile(rf"V\.S\s+({_NUM})m/s")
_BARO = re.compile(rf"BAROMETER\s*:\s*({_NUM})")
_PRY = re.compile(rf"([FG])\.PRY\s*\(\s*({_NUM})°?\s*,\s*({_NUM})°?\s*,\s*({_NUM})°?\s*\)")
_DEVICE_TIME = re.compile(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})(?:[.,](\d{1,3}))?")

LAT_KEYS = {"latitude"}
LON_KEYS = {"longitude", "longtitude"}


@dataclass
class TelemetryFrame:
    index: int
    start_s: float | None = None
    end_s: float | None = None
    device_time: str | None = None       # drone clock, time zone NOT recorded in the file
    latitude: float | None = None
    longitude: float | None = None
    relative_altitude_m: float | None = None
    absolute_altitude_m: float | None = None
    altitude_m: float | None = None      # altitude with unstated reference
    barometric_height_m: float | None = None
    height_m: float | None = None        # "H" in compact format
    distance_from_home_m: float | None = None
    horizontal_speed_m_s: float | None = None
    vertical_speed_m_s: float | None = None
    home: tuple[float, float] | None = None
    aircraft_pitch_roll_yaw: tuple[float, float, float] | None = None
    gimbal_pitch_roll_yaw: tuple[float, float, float] | None = None
    positional_gps: tuple[float, float] | None = None
    positional_gps_third: str | None = None
    raw: str = ""


@dataclass
class SrtTelemetry:
    frames: list[TelemetryFrame] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    gps_axis_order: str = "not_applicable"   # keyed | lon_lat | lat_lon | ambiguous | inconsistent
    gps_axis_order_source: str | None = None
    warnings: list[str] = field(default_factory=list)


def _f(text: str | None) -> float | None:
    try:
        return float(text) if text is not None else None
    except ValueError:
        return None


def _valid(lat: float | None, lon: float | None) -> bool:
    return (lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180
            and not (lat == 0 and lon == 0))


def _blocks(text: str) -> list[list[str]]:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    return [[ln.strip() for ln in b.split("\n") if ln.strip()] for b in re.split(r"\n\s*\n", text) if b.strip()]


def parse_text(text: str, gps_axis_order: str | None = None) -> SrtTelemetry:
    """gps_axis_order: optional examiner override, 'lon_lat' or 'lat_lon'."""
    out = SrtTelemetry()
    formats: set[str] = set()
    for n, lines in enumerate(_blocks(text), start=1):
        frame = TelemetryFrame(index=n)
        body_lines = list(lines)
        if body_lines and body_lines[0].isdigit():
            frame.index = int(body_lines.pop(0))
        if body_lines:
            m = _TIMECODE.search(body_lines[0])
            if m:
                g = [int(x) for x in m.groups()]
                frame.start_s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
                frame.end_s = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
                body_lines.pop(0)
        body = _TAG.sub(" ", " ".join(body_lines))
        frame.raw = body.strip()

        dt = _DEVICE_TIME.search(body)
        if dt:
            y, mo, d, h, mi, s, frac = dt.groups()
            ms = f".{frac.ljust(3, '0')[:3]}" if frac else ""
            frame.device_time = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}T{int(h):02d}:{mi}:{s}{ms}"

        keyed = {}
        for inner in _BRACKET.findall(body):
            for k, v in _KEYVAL.findall(inner):
                keyed[k.lower()] = v
        if keyed:
            formats.add("keyed")
            lat = next((_f(keyed[k]) for k in LAT_KEYS if k in keyed), None)
            lon = next((_f(keyed[k]) for k in LON_KEYS if k in keyed), None)
            if _valid(lat, lon):
                frame.latitude, frame.longitude = lat, lon
            frame.relative_altitude_m = _f(keyed.get("rel_alt"))
            frame.absolute_altitude_m = _f(keyed.get("abs_alt"))
            frame.altitude_m = _f(keyed.get("altitude"))

        m = _GPS.search(body)
        if m:
            formats.add("positional")
            frame.positional_gps = (float(m.group(1)), float(m.group(2)))
            if m.group(3) is not None:
                if m.group(4):   # explicit metre unit -> altitude
                    frame.altitude_m = float(m.group(3))
                else:            # meaning differs by model (satellites / altitude)
                    frame.positional_gps_third = m.group(3)
        h = _HOME.search(body)
        if h:
            frame.home = (float(h.group(1)), float(h.group(2)))
        for rx, attr in ((_DIST, "distance_from_home_m"), (_HEIGHT, "height_m"),
                         (_HSPEED, "horizontal_speed_m_s"), (_VSPEED, "vertical_speed_m_s"),
                         (_BARO, "barometric_height_m")):
            mm = rx.search(body)
            if mm:
                setattr(frame, attr, float(mm.group(1)))
        for kind, p, r, y in _PRY.findall(body):
            attr = "aircraft_pitch_roll_yaw" if kind == "F" else "gimbal_pitch_roll_yaw"
            setattr(frame, attr, (float(p), float(r), float(y)))
        out.frames.append(frame)

    out.formats = sorted(formats)
    _resolve_positional(out, gps_axis_order)
    if not out.frames:
        out.warnings.append("no telemetry frames found")
    elif not any(f.latitude is not None for f in out.frames):
        out.warnings.append("no frame carries a usable position")
    return out


def _resolve_positional(out: SrtTelemetry, override: str | None) -> None:
    pairs = [f.positional_gps for f in out.frames if f.positional_gps]
    pairs += [f.home for f in out.frames if f.home]
    if not pairs:
        out.gps_axis_order = "keyed" if "keyed" in out.formats else "not_applicable"
        return
    first_is_lon = any(abs(a) > 90 for a, _ in pairs)
    second_is_lon = any(abs(b) > 90 for _, b in pairs)
    if override in ("lon_lat", "lat_lon"):
        order, source = override, "examiner_override"
        if (override == "lat_lon" and first_is_lon) or (override == "lon_lat" and second_is_lon):
            out.warnings.append("examiner axis-order override contradicts the recorded values")
    elif first_is_lon and not second_is_lon:
        order, source = "lon_lat", "value_range"
    elif second_is_lon and not first_is_lon:
        order, source = "lat_lon", "value_range"
    elif first_is_lon and second_is_lon:
        order, source = "inconsistent", "value_range"
    else:
        order, source = _order_from_keyed_frames(out), "keyed_frames_in_same_file"
        if order is None:
            order, source = "ambiguous", None
    out.gps_axis_order, out.gps_axis_order_source = order, source

    if order not in ("lon_lat", "lat_lon"):
        out.warnings.append(
            f"positional GPS axis order is {order}: both values lie within +-90 degrees, "
            "so latitude/longitude were not assigned (raw pairs kept); "
            "supply gps_axis_order after checking against another source")
        return
    for f in out.frames:
        if f.positional_gps and f.latitude is None:
            a, b = f.positional_gps
            lat, lon = (b, a) if order == "lon_lat" else (a, b)
            if _valid(lat, lon):
                f.latitude, f.longitude = lat, lon


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


def _order_from_keyed_frames(out: SrtTelemetry) -> str | None:
    """
    Some files mix keyed frames (explicit latitude/longitude) with positional
    ones. If the positional pairs sit within 1 km of the keyed positions under
    one order and over 100 km away under the other, that order is proven.
    """
    keyed = [(f.latitude, f.longitude) for f in out.frames
             if f.latitude is not None and not f.positional_gps]
    pos = [f.positional_gps for f in out.frames if f.positional_gps]
    if not keyed or not pos:
        return None
    ref_lat, ref_lon = keyed[0]
    a, b = pos[0]
    d_lon_lat = _haversine_km(b, a, ref_lat, ref_lon) if -90 <= b <= 90 else float("inf")
    d_lat_lon = _haversine_km(a, b, ref_lat, ref_lon) if -90 <= a <= 90 else float("inf")
    if d_lon_lat < 1 and d_lat_lon > 100:
        return "lon_lat"
    if d_lat_lon < 1 and d_lon_lat > 100:
        return "lat_lon"
    return None


def parse_file(path: str, gps_axis_order: str | None = None, max_bytes: int = 200 * 1024 * 1024) -> SrtTelemetry:
    with open(path, "rb") as fh:
        data = fh.read(max_bytes)
    text = data.decode("utf-8", "replace")
    result = parse_text(text, gps_axis_order)
    if len(data) == max_bytes:
        result.warnings.append(f"file larger than {max_bytes} bytes; only the first part was parsed")
    return result


def summarize(t: SrtTelemetry) -> dict[str, Any]:
    with_pos = [f for f in t.frames if f.latitude is not None]
    times = [f.device_time for f in t.frames if f.device_time]
    return {
        "frame_count": len(t.frames),
        "frames_with_position": len(with_pos),
        "formats": t.formats,
        "gps_axis_order": t.gps_axis_order,
        "gps_axis_order_source": t.gps_axis_order_source,
        "first_device_time": times[0] if times else None,
        "last_device_time": times[-1] if times else None,
        "first_position": [with_pos[0].latitude, with_pos[0].longitude] if with_pos else None,
        "warnings": t.warnings,
    }
