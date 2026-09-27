"""
MP4 / QuickTime metadata without loading the video into memory.

Reads the ISO-BMFF box tree by seeking: creation/modification time and
duration from 'mvhd', ISO-6709 location strings ('\\xa9xyz' or the
com.apple.quicktime.location.ISO6709 key), and make/model/encoder strings.
Embedded GPS tracks (e.g. GoPro GPMF, DJI 'djmd') are proprietary and are
NOT decoded; for DJI, per-frame telemetry is taken from the .SRT sidecar.
"""

from __future__ import annotations

import re
import struct
from datetime import datetime, timedelta, timezone
from typing import Any, BinaryIO

_CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"udta", b"edts", b"meta", b"ilst"}
_EPOCH_1904 = datetime(1904, 1, 1, tzinfo=timezone.utc)
_ISO6709 = re.compile(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)?")
_STRING_ATOMS = {b"\xa9mak": "make", b"\xa9mod": "model", b"\xa9too": "encoder",
                 b"\xa9swr": "software", b"\xa9day": "date"}
MAX_BOXES = 5000


def _boxes(fh: BinaryIO, start: int, end: int):
    pos = start
    count = 0
    while pos + 8 <= end and count < MAX_BOXES:
        fh.seek(pos)
        head = fh.read(8)
        if len(head) < 8:
            return
        size, btype = struct.unpack(">I4s", head)
        header = 8
        if size == 1:
            ext = fh.read(8)
            if len(ext) < 8:
                return
            size = struct.unpack(">Q", ext)[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            return  # truncated or corrupt: stop rather than guess
        yield btype, pos, pos + header, pos + size
        pos += size
        count += 1


def _mvhd(fh: BinaryIO, body: int) -> dict[str, Any]:
    fh.seek(body)
    version = fh.read(1)[0]
    fh.read(3)
    if version == 1:
        created, modified, timescale, duration = struct.unpack(">QQIQ", fh.read(28))
    else:
        created, modified, timescale, duration = struct.unpack(">IIII", fh.read(16))

    def ts(v: int) -> str | None:
        return (_EPOCH_1904 + timedelta(seconds=v)).isoformat() if v else None

    return {"creation_time_utc": ts(created), "modification_time_utc": ts(modified),
            "duration_s": duration / timescale if timescale else None}


def _string_atom(fh: BinaryIO, body: int, end: int) -> str | None:
    fh.seek(body)
    raw = fh.read(min(end - body, 4096))
    if raw[4:8] == b"data" and len(raw) >= 16:        # iTunes-style 'data' child
        text = raw[16:]
    elif len(raw) >= 4:                               # QuickTime: size(2) lang(2) text
        (length,) = struct.unpack(">H", raw[:2])
        text = raw[4:4 + length]
    else:
        return None
    return text.decode("utf-8", "replace").replace("\x00", "").strip() or None


def parse_iso6709(text: str) -> dict[str, float] | None:
    m = _ISO6709.match(text.strip())
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    out = {"latitude": lat, "longitude": lon}
    if m.group(3):
        out["altitude_m"] = float(m.group(3))
    return out


def read(path: str) -> dict[str, Any]:
    result: dict[str, Any] = {"errors": [], "strings": {}}
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            keys: list[str] = []
            stack = [(0, size)]
            while stack:
                start, end = stack.pop()
                for btype, pos, body, bend in _boxes(fh, start, end):
                    if btype == b"ftyp":
                        fh.seek(body)
                        result["major_brand"] = fh.read(4).decode("latin-1").strip()
                    elif btype == b"mvhd":
                        result.update(_mvhd(fh, body))
                    elif btype == b"\xa9xyz":
                        text = _string_atom(fh, body, bend)
                        if text:
                            result["location_raw"] = text
                            loc = parse_iso6709(text)
                            if loc:
                                result["location"] = loc
                    elif btype in _STRING_ATOMS:
                        text = _string_atom(fh, body, bend)
                        if text:
                            result["strings"][_STRING_ATOMS[btype]] = text
                    elif btype == b"keys":
                        fh.seek(body + 8)
                        blob = fh.read(min(bend - body - 8, 65536))
                        keys = re.findall(rb"mdta([\x20-\x7e]+?)(?=\x00|$)", blob)
                        keys = [k.decode("ascii", "replace") for k in keys]
                        result["metadata_keys"] = keys
                    elif btype == b"meta":
                        # MP4 'meta' is a full box (4 bytes version/flags before
                        # its children); QuickTime 'meta' is not.
                        fh.seek(body)
                        peek = fh.read(8)
                        child_first = peek[4:8] in (b"hdlr", b"keys", b"ilst")
                        stack.append((body if child_first else body + 4, bend))
                    elif btype in _CONTAINERS:
                        stack.append((body, bend))
            if keys and "location" not in result:
                _quicktime_keyed_location(fh, size, keys, result)
    except (OSError, struct.error, IndexError) as exc:
        result["errors"].append(f"video parse failed: {type(exc).__name__}: {exc}")
    return result


def _quicktime_keyed_location(fh: BinaryIO, size: int, keys: list[str], result: dict) -> None:
    """Apple-style keyed metadata: find the ISO6709 string by value pattern."""
    if "com.apple.quicktime.location.ISO6709" not in keys:
        return
    fh.seek(0)
    blob = fh.read(min(size, 8 * 1024 * 1024))
    m = re.search(rb"[+-]\d{1,2}\.\d+[+-]\d{1,3}\.\d+(?:[+-]\d+(?:\.\d+)?)?/", blob)
    if m:
        text = m.group(0).decode("ascii")
        result["location_raw"] = text
        loc = parse_iso6709(text)
        if loc:
            result["location"] = loc
