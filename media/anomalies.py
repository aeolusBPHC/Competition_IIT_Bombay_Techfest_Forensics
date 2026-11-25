"""Evidence-preserving anomaly checks for media reports.

Flags describe observable inconsistencies; they do not assert tampering. Time
comparisons are restricted to a single clock basis, and source values remain
attached to every finding.
"""

from __future__ import annotations

import math
import re
from typing import Any

from media.normalize import haversine_m

POSITION_DISAGREEMENT_M = 50.0
IMPLAUSIBLE_GROUND_SPEED_M_S = 100.0
IMPLAUSIBLE_VERTICAL_SPEED_M_S = 60.0


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _xmp_positions(values: dict[str, Any]) -> list[dict[str, Any]]:
    lat_names = {"gpslatitude", "latitude"}
    lon_names = {"gpslongitude", "gpslongtitude", "longitude", "longtitude"}
    props: dict[str, list[tuple[float, str]]] = {"lat": [], "lon": []}
    for qualified, value in values.items():
        local = re.sub(r".*[}:]", "", str(qualified)).lower()
        axis = "lat" if local in lat_names else "lon" if local in lon_names else None
        number = _number(value)
        if axis and number is not None:
            props[axis].append((number, str(qualified)))
    candidates = []
    for lat, lat_src in props["lat"]:
        for lon, lon_src in props["lon"]:
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                candidates.append({"source": "XMP", "latitude": lat, "longitude": lon,
                                   "source_tags": [lat_src, lon_src]})
    return candidates


def _positions(item: dict[str, Any]) -> list[dict[str, Any]]:
    md = item.get("metadata") or {}
    raw = md.get("raw") or {}
    candidates = _xmp_positions(raw.get("xmp") or {})
    fields = md.get("fields") or {}
    selected = {axis: (fields.get(axis) or {}).get("value") for axis in ("latitude", "longitude")}
    sources = {str((fields.get(axis) or {}).get("source", "")) for axis in ("latitude", "longitude")}
    if all(_number(selected[a]) is not None for a in selected):
        lat, lon = (_number(selected[a]) for a in ("latitude", "longitude"))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            candidates.append({"source": "+".join(sorted(s for s in sources if s)) or "normalized",
                               "latitude": lat, "longitude": lon})
    loc = (raw.get("container") or {}).get("location") or {}
    lat, lon = _number(loc.get("latitude")), _number(loc.get("longitude"))
    if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
        candidates.append({"source": "QuickTime:ISO6709", "latitude": lat,
                           "longitude": lon})
    # The normalized EXIF GPS value is kept in `fields`; no need to reinterpret
    # the raw DMS rationals and risk losing their reference/sign semantics.
    unique = {}
    for point in candidates:
        key = (round(point["latitude"], 8), round(point["longitude"], 8), point["source"])
        unique[key] = point
    return list(unique.values())


def _position_disagreements(item: dict[str, Any], threshold_m: float = POSITION_DISAGREEMENT_M) -> list[dict[str, Any]]:
    positions = _positions(item)
    findings = []
    for index, left in enumerate(positions):
        for right in positions[index + 1:]:
            distance = haversine_m(left["latitude"], left["longitude"],
                                   right["latitude"], right["longitude"])
            if distance > threshold_m:
                findings.append({"type": "LOCATION_METADATA_DISAGREEMENT",
                                 "severity": "warning", "distance_m": round(distance, 1),
                                 "sources": [left["source"], right["source"]],
                                 "positions": [left, right],
                                 "threshold_m": threshold_m,
                                 "note": "Independent location metadata differs; this is an observation, not a conclusion."})
    # A single embedded fix can be compared to file-level coordinates without
    # assuming anything about aircraft movement. For a multi-sample track,
    # temporal alignment is required and is deliberately not guessed here.
    gps_samples = [sample for sample in ((item.get("embedded_telemetry") or {}).get("samples") or [])
                   if _number(((sample.get("gps") or {}).get("latitude"))) is not None
                   and _number(((sample.get("gps") or {}).get("longitude"))) is not None]
    if len(gps_samples) == 1:
        gps = gps_samples[0]["gps"]
        lat, lon = _number(gps.get("latitude")), _number(gps.get("longitude"))
        compared = set()
        for point in positions:
            key = (point["latitude"], point["longitude"])
            if key in compared:
                continue
            compared.add(key)
            distance = haversine_m(point["latitude"], point["longitude"], lat, lon)
            if distance > threshold_m:
                findings.append({"type": "LOCATION_METADATA_DISAGREEMENT",
                                 "severity": "warning", "distance_m": round(distance, 1),
                                 "sources": [point["source"], "embedded_video_telemetry"],
                                 "positions": [point, {"source": "embedded_video_telemetry",
                                                       "latitude": lat, "longitude": lon,
                                                       "sample_index": gps_samples[0].get("index")}],
                                 "threshold_m": threshold_m,
                                 "note": "Single embedded fix differs from file-level location; temporal alignment and movement are not established."})
    return findings


def _timestamp_gaps(entries: list[tuple[float, dict]], *, source: str,
                    expected_step: float | None = None) -> list[dict[str, Any]]:
    ordering = []
    for (previous, previous_detail), (current, current_detail) in zip(entries, entries[1:]):
        if current < previous:
            ordering.append({"type": "NON_MONOTONIC_TIMESTAMP", "severity": "warning",
                             "confidence": "high", "source": source,
                             "previous_s": previous, "current_s": current,
                             "previous": previous_detail, "current": current_detail,
                             "note": "Source-order timestamps move backwards on the stated clock."})
        elif current == previous:
            ordering.append({"type": "DUPLICATE_TIMESTAMP", "severity": "info",
                             "confidence": "high", "source": source,
                             "timestamp_s": current, "previous": previous_detail,
                             "current": current_detail,
                             "note": "Two observations share a timestamp; clock resolution or duplicate records may explain this."})
    ordered = sorted(((t, row) for t, row in entries if math.isfinite(t)), key=lambda pair: pair[0])
    deltas = [b[0] - a[0] for a, b in zip(ordered, ordered[1:]) if b[0] > a[0]]
    if expected_step is None and len(deltas) >= 3:
        expected_step = sorted(deltas)[len(deltas) // 2]
    if expected_step is None or expected_step <= 0:
        return ordering
    threshold = max(expected_step * 3.0, expected_step + 0.5)
    findings = list(ordering)
    for (t0, before), (t1, after) in zip(ordered, ordered[1:]):
        delta = t1 - t0
        if delta > threshold:
            findings.append({"type": "TIMESTAMP_GAP", "severity": "warning",
                             "source": source, "start_s": t0, "end_s": t1,
                             "gap_s": round(delta, 6), "expected_step_s": round(expected_step, 6),
                             "threshold_s": round(threshold, 6),
                             "before": before, "after": after,
                             "note": "A timing gap was detected on the stated clock; missing evidence is not inferred."})
    return findings


def _jumps(entries: list[tuple[float, float, float, dict]], *, source: str,
           time_basis: str, threshold_m_s: float = IMPLAUSIBLE_GROUND_SPEED_M_S) -> list[dict[str, Any]]:
    ordered = sorted(entries, key=lambda p: p[0])
    findings = []
    for a, b in zip(ordered, ordered[1:]):
        delta = b[0] - a[0]
        if delta <= 0:
            continue
        distance = haversine_m(a[1], a[2], b[1], b[2])
        speed = distance / delta
        if speed > threshold_m_s:
            findings.append({"type": "LOCATION_JUMP", "severity": "warning", "source": source,
                             "time_basis": time_basis, "distance_m": round(distance, 1),
                             "elapsed_s": round(delta, 6), "implied_speed_m_s": round(speed, 2),
                             "threshold_m_s": threshold_m_s,
                             "from": a[3], "to": b[3],
                             "note": "Positions imply unusually high ground speed; verify clocks, coordinate source, and parsing."})
    return findings


def analyze_item(item: dict[str, Any], *, position_disagreement_m: float = POSITION_DISAGREEMENT_M,
                 max_ground_speed_m_s: float = IMPLAUSIBLE_GROUND_SPEED_M_S,
                 max_vertical_speed_m_s: float = IMPLAUSIBLE_VERTICAL_SPEED_M_S) -> list[dict[str, Any]]:
    """Return findings for one serialized MediaItem."""
    findings = _position_disagreements(item, position_disagreement_m)
    for finding in findings:
        finding["confidence"] = "low"  # independent metadata can describe different capture moments
        finding["threshold_m"] = position_disagreement_m
    timeline = item.get("frame_timeline") or {}
    findings.extend(timeline.get("timestamp_order_findings") or [])
    frames = timeline.get("frames") or []
    frame_entries = []
    for frame in frames:
        t = _number(frame.get("pts_s"))
        if t is not None:
            frame_entries.append((t, {"frame_number": frame.get("frame_number")}))
    expected = _number(timeline.get("interval_s"))
    findings.extend(_timestamp_gaps(frame_entries, source="video_presentation_time", expected_step=expected))

    sidecar = item.get("telemetry") or {}
    srt_frames = sidecar.get("frames") or []
    srt_times, srt_points = [], []
    for frame in srt_frames:
        t = _number(frame.get("start_s"))
        if t is None:
            continue
        srt_times.append((t, {"frame": frame.get("index")}))
        lat, lon = _number(frame.get("latitude")), _number(frame.get("longitude"))
        if lat is not None and lon is not None:
            srt_points.append((t, lat, lon, {"frame": frame.get("index")}))
    findings.extend(_timestamp_gaps(srt_times, source="SRT_video_relative_time"))
    findings.extend(_jumps(srt_points, source="SRT", time_basis="video_relative_time_seconds",
                           threshold_m_s=max_ground_speed_m_s))

    embedded = item.get("embedded_telemetry") or {}
    samples = embedded.get("samples") or []
    timed, points = [], []
    basis = None
    for sample in samples:
        timestamp = sample.get("timestamp") or {}
        value = _number(timestamp.get("value"))
        current_basis = timestamp.get("basis")
        if value is None or not current_basis:
            continue
        if basis is None:
            basis = current_basis
        if current_basis != basis:
            continue
        detail = {"sample_index": sample.get("index"), "timestamp": timestamp}
        timed.append((value, detail))
        gps = sample.get("gps") or {}
        lat, lon = _number(gps.get("latitude")), _number(gps.get("longitude"))
        if lat is not None and lon is not None:
            points.append((value, lat, lon, detail))
    findings.extend(_timestamp_gaps(timed, source=f"embedded_telemetry:{basis or 'unknown'}"))
    findings.extend(_jumps(points, source="embedded_telemetry", time_basis=basis or "source_clock",
                           threshold_m_s=max_ground_speed_m_s))
    findings.extend(_altitude_jumps(samples, max_vertical_speed_m_s))
    for finding in findings:
        finding.setdefault("severity", "warning")
        finding.setdefault("confidence", "medium" if finding["type"] in {
            "LOCATION_JUMP", "ALTITUDE_JUMP", "TIMESTAMP_GAP"} else "low")
    return findings


def _altitude_jumps(samples: list[dict[str, Any]], threshold_m_s: float) -> list[dict[str, Any]]:
    """Compare same-reference altitude samples on the same explicit clock."""
    groups: dict[tuple[str, str], list[tuple[float, float, dict[str, Any]]]] = {}
    for sample in samples:
        stamp = sample.get("timestamp") or {}
        t, basis = _number(stamp.get("value")), stamp.get("basis")
        if t is None or not basis:
            continue
        for reference, field in (sample.get("altitude") or {}).items():
            value = field if isinstance(field, dict) else {}
            altitude = _number(value.get("value"))
            if altitude is None or value.get("units") != "m":
                continue
            groups.setdefault((str(basis), str(reference)), []).append(
                (t, altitude, {"sample_index": sample.get("index"),
                               "timestamp": stamp, "altitude": value})
            )
    findings = []
    for (basis, reference), entries in groups.items():
        # Keep source order to expose clock resets instead of sorting them away.
        for a, b in zip(entries, entries[1:]):
            dt = b[0] - a[0]
            if dt <= 0:
                continue
            delta = abs(b[1] - a[1])
            rate = delta / dt
            if rate > threshold_m_s:
                findings.append({"type": "ALTITUDE_JUMP", "severity": "warning",
                                 "confidence": "medium", "source": "embedded_video_telemetry",
                                 "time_basis": basis, "altitude_reference": reference,
                                 "from": a[2], "to": b[2], "delta_m": round(delta, 3),
                                 "elapsed_s": round(dt, 6), "implied_vertical_speed_m_s": round(rate, 2),
                                 "threshold_m_s": threshold_m_s,
                                 "note": "Altitude samples imply an unusually high vertical rate; verify units, datum, and clock."})
    return findings

