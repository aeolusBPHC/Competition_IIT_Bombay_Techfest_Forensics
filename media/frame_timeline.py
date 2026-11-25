"""Build a bounded, presentation-time frame index for video evidence.

Frame timestamps are offsets on the video's media clock. They are not wall-clock
capture times unless another source independently establishes that relationship.
The implementation uses ffprobe when available and never modifies the source.
"""

from __future__ import annotations

import json
import base64
import math
import shutil
import subprocess
from typing import Any

MAX_FRAME_THUMBNAILS = 500


def _number(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _jpeg_images(payload: bytes) -> list[bytes]:
    """Split concatenated MJPEG output into individual JPEG images."""
    images = []
    start = 0
    while True:
        start = payload.find(b"\xff\xd8", start)
        if start < 0:
            break
        end = payload.find(b"\xff\xd9", start + 2)
        if end < 0:
            break
        images.append(payload[start:end + 2])
        start = end + 2
    return images


def _attach_thumbnails(path: str, frames: list[dict[str, Any]], *, timeout_s: int) -> str | None:
    """Extract small rotated JPEG previews in batches, preserving frame order."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not frames:
        return "ffmpeg is unavailable; frame thumbnails were not generated" if frames else None
    thumbnail_frames = frames[:MAX_FRAME_THUMBNAILS]
    # Keep command lines bounded. ffmpeg auto-applies display-matrix rotation
    # unless -noautorotate is supplied; the preview follows normal playback.
    for offset in range(0, len(thumbnail_frames), 128):
        batch = thumbnail_frames[offset:offset + 128]
        expression = "+".join(f"eq(n\\,{int(frame['frame_number'])})" for frame in batch)
        command = [ffmpeg, "-v", "error", "-i", path, "-an", "-vf",
                   f"select='{expression}',scale=320:-2", "-vsync", "0", "-q:v", "6",
                   "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"]
        try:
            proc = subprocess.run(command, capture_output=True, timeout=timeout_s, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"frame thumbnail extraction failed: {type(exc).__name__}"
        if proc.returncode:
            detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
            return "frame thumbnail extraction failed" + (f": {detail[-1][:200]}" if detail else "")
        images = _jpeg_images(proc.stdout)
        for frame, image in zip(batch, images):
            frame["thumbnail_data_uri"] = "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")
        if len(images) != len(batch):
            return f"ffmpeg returned {len(images)} thumbnails for {len(batch)} selected frames"
    if len(frames) > MAX_FRAME_THUMBNAILS:
        return f"thumbnail limit reached; previews generated for the first {MAX_FRAME_THUMBNAILS} of {len(frames)} indexed frames"
    return None


def build(path: str, interval_s: float | None = 1.0, *, ffprobe: str | None = None,
          timeout_s: int = 600, source_path: str | None = None,
          source_sha256: str | None = None) -> dict[str, Any]:
    """Return sampled video frame timing and stream details.

    ``interval_s`` selects the first decodable frame at or after each interval
    boundary. Pass ``None`` to retain every frame. A missing ffprobe or malformed
    output is represented in the returned status/warnings, not raised to callers.
    """
    if interval_s is not None and (not math.isfinite(interval_s) or interval_s <= 0):
        raise ValueError("interval_s must be positive or None")

    executable = ffprobe or shutil.which("ffprobe")
    base: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "unavailable",
        "timestamp_basis": "video_presentation_time_seconds",
        "interval_s": interval_s,
        "frames": [],
        "warnings": [],
        "source_path": source_path or path,
        "source_sha256": source_sha256,
        "thumbnail_method": "ffmpeg decoded JPEG preview; display rotation applied when present",
    }
    if not executable:
        base["warnings"].append("ffprobe is not installed; frame timeline was not generated")
        return base

    command = [
        executable, "-v", "error", "-select_streams", "v:0", "-show_streams",
        "-show_frames", "-show_entries",
        "stream=index,codec_name,width,height,r_frame_rate,avg_frame_rate,time_base,start_time,duration,nb_frames:"
        "stream_tags=rotate:"
        "frame=best_effort_timestamp_time,pts_time,pkt_pts_time,pkt_duration_time,"
        "key_frame,pict_type,width,height",
        "-of", "json", path,
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s,
                              check=False)
    except subprocess.TimeoutExpired:
        base["status"] = "error"
        base["warnings"].append(f"ffprobe timed out after {timeout_s} seconds")
        return base
    except OSError as exc:
        base["status"] = "error"
        base["warnings"].append(f"could not run ffprobe: {type(exc).__name__}: {exc}")
        return base

    if proc.returncode != 0:
        base["status"] = "error"
        detail = proc.stderr.strip().splitlines()
        base["warnings"].append("ffprobe failed" + (f": {detail[-1][:300]}" if detail else ""))
        return base
    try:
        parsed = json.loads(proc.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        base["status"] = "error"
        base["warnings"].append(f"ffprobe returned invalid JSON: {exc}")
        return base

    streams = parsed.get("streams") or []
    if streams:
        stream = streams[0]
        base["stream"] = {
            key: stream[key] for key in (
                "index", "codec_name", "width", "height", "r_frame_rate",
                "avg_frame_rate", "time_base", "start_time", "duration", "nb_frames",
            ) if key in stream
        }
        side_data = stream.get("side_data_list") or []
        rotation = next((entry.get("rotation") for entry in side_data
                         if entry.get("rotation") is not None), None)
        rotation = rotation if rotation is not None else (stream.get("tags") or {}).get("rotate")
        if rotation is not None:
            base["stream"]["display_rotation_degrees"] = _number(rotation)
        # FFmpeg 4.x cannot select nested stream_side_data fields through
        # -show_entries. Query the lightweight stream record separately.
        try:
            meta = subprocess.run(
                [executable, "-v", "error", "-select_streams", "v:0",
                 "-show_streams", "-of", "json", path],
                capture_output=True, text=True, timeout=30, check=False,
            )
            if meta.returncode == 0:
                meta_streams = json.loads(meta.stdout).get("streams") or []
                if meta_streams:
                    detailed = meta_streams[0]
                    side_data = detailed.get("side_data_list") or []
                    rotation = next((entry.get("rotation") for entry in side_data
                                     if entry.get("rotation") is not None), None)
                    rotation = rotation if rotation is not None else (detailed.get("tags") or {}).get("rotate")
                    if rotation is not None:
                        base["stream"]["display_rotation_degrees"] = _number(rotation)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            base["warnings"].append("ffprobe could not inspect display rotation metadata")

    frames = parsed.get("frames") or []
    selected: list[dict[str, Any]] = []
    origin_pts: float | None = None
    next_boundary: float | None = None
    untimed = 0
    previous_pts: float | None = None
    previous_timed_frame: int | None = None
    order_findings = []
    for ordinal, frame in enumerate(frames):
        pts_source = next((key for key in (
            "best_effort_timestamp_time", "pts_time", "pkt_pts_time",
        ) if _number(frame.get(key)) is not None), None)
        pts = _number(frame.get(pts_source)) if pts_source else None
        if pts is None:
            untimed += 1
            continue
        if previous_pts is not None and pts <= previous_pts:
            order_findings.append({
                "type": "NON_MONOTONIC_TIMESTAMP" if pts < previous_pts else "DUPLICATE_TIMESTAMP",
                "severity": "warning" if pts < previous_pts else "info",
                "confidence": "high", "source": "video_presentation_time",
                "previous_frame": previous_timed_frame, "frame_number": ordinal,
                "previous_pts_s": previous_pts, "pts_s": pts,
                "timestamp_basis": "video_presentation_time_seconds",
            })
        previous_pts = pts
        previous_timed_frame = ordinal
        if origin_pts is None:
            origin_pts = pts
            next_boundary = pts
        if interval_s is not None:
            if pts + 1e-9 < (next_boundary if next_boundary is not None else pts):
                continue
            # Boundaries are relative to the first timed frame, not to zero on
            # the media clock (which may start at a non-zero/negative PTS).
            elapsed = max(0.0, pts - origin_pts)
            next_boundary = origin_pts + (math.floor(elapsed / interval_s) + 1) * interval_s
        selected.append({
            "frame_number": ordinal,
            "pts_s": pts,
            "timestamp_source": pts_source,
            "offset_s": pts - origin_pts,
            "timestamp_basis": "video_presentation_time_seconds",
            "duration_s": _number(frame.get("pkt_duration_time")),
            "key_frame": bool(int(frame.get("key_frame", 0) or 0)),
            "picture_type": frame.get("pict_type"),
            "width": frame.get("width"),
            "height": frame.get("height"),
        })

    base["status"] = "ok"
    base["frames"] = selected
    thumbnail_warning = _attach_thumbnails(path, selected, timeout_s=timeout_s)
    if thumbnail_warning:
        base["warnings"].append(thumbnail_warning)
    base["frame_count_decoded"] = len(frames)
    base["frame_count_timed"] = len(frames) - untimed
    base["frame_count_indexed"] = len(selected)
    base["timestamp_order_findings"] = order_findings
    base["timeline_start_pts_s"] = origin_pts
    if untimed:
        base["warnings"].append(f"{untimed} decoded frames had no usable presentation timestamp")
    if not frames:
        base["warnings"].append("ffprobe found no decodable video frames")
    return base
