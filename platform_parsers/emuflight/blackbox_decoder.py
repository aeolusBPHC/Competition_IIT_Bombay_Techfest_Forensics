"""
Generic Blackbox (Cleanflight / Betaflight / EmuFlight lineage) binary decoder.

This module is deliberately platform-agnostic: it turns the bytes of a
Blackbox log into generic frames (dicts of field name -> integer value)
and events. It knows NOTHING about GPS, batteries or the normalized
evidence model. Mapping into forensic records happens in the parser.

Format references: the open-source blackbox-tools decoder (parser.c,
decoders.c) and the Betaflight blackbox writer. The encodings and
predictors below follow those implementations.

Forensic properties:
  * Every decoded frame keeps its byte offset in the source file.
  * Frames that fail validation are counted and discarded, never repaired.
  * P-frames are rejected until a valid I-frame re-establishes history,
    so a corrupt region can never silently poison later values.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

LOG_START_MARKER = b"H Product:Blackbox flight data recorder"

# ---------------------------------------------------------------- encodings
ENC_SIGNED_VB = 0
ENC_UNSIGNED_VB = 1
ENC_NEG_14BIT = 3
ENC_TAG8_8SVB = 6
ENC_TAG2_3S32 = 7
ENC_TAG8_4S16 = 8
ENC_NULL = 9
ENC_TAG2_3SVARIABLE = 10

# --------------------------------------------------------------- predictors
PRED_ZERO = 0
PRED_PREVIOUS = 1
PRED_STRAIGHT_LINE = 2
PRED_AVERAGE_2 = 3
PRED_MINTHROTTLE = 4
PRED_MOTOR_0 = 5
PRED_INC = 6
PRED_HOME_COORD = 7
PRED_1500 = 8
PRED_VBATREF = 9
PRED_LAST_MAIN_FRAME_TIME = 10
PRED_MINMOTOR = 11

# ------------------------------------------------------------------ events
EVENT_SYNC_BEEP = 0
EVENT_INFLIGHT_ADJUSTMENT = 13
EVENT_LOGGING_RESUME = 14
EVENT_DISARM = 15
EVENT_FLIGHT_MODE = 30
EVENT_LOG_END = 255

EVENT_NAMES = {
    EVENT_SYNC_BEEP: "SYNC_BEEP",
    EVENT_INFLIGHT_ADJUSTMENT: "INFLIGHT_ADJUSTMENT",
    EVENT_LOGGING_RESUME: "LOGGING_RESUME",
    EVENT_DISARM: "DISARM",
    EVENT_FLIGHT_MODE: "FLIGHT_MODE",
    EVENT_LOG_END: "LOG_END",
}

FRAME_MARKERS = {ord("I"), ord("P"), ord("G"), ord("H"), ord("S"), ord("E")}

# Plausibility limits (same values as the blackbox-tools reference decoder).
# Blackbox has no checksums, so these structural checks are the only
# corruption detection the format allows.
MAX_TIME_JUMP_US = 10_000_000
MAX_ITERATION_JUMP = 500 * 10


class BlackboxDecodeError(Exception):
    """Raised when a frame cannot be decoded (truncation, unknown event...)."""


# ------------------------------------------------------------------ helpers
def _sign_extend(value: int, bits: int) -> int:
    sign_bit = 1 << (bits - 1)
    value &= (1 << bits) - 1
    return value - (1 << bits) if value & sign_bit else value


def _wrap32(value: int, signed: bool) -> int:
    value &= 0xFFFFFFFF
    if signed and value & 0x80000000:
        value -= 1 << 32
    return value


def _trunc_div2(value: int) -> int:
    """C-style integer division by 2 (truncates toward zero)."""
    q = abs(value) // 2
    return q if value >= 0 else -q


class _Reader:
    def __init__(self, data: bytes, pos: int):
        self.data = data
        self.pos = pos

    def byte(self) -> int:
        if self.pos >= len(self.data):
            raise BlackboxDecodeError("unexpected end of data")
        b = self.data[self.pos]
        self.pos += 1
        return b

    def uvb(self) -> int:
        result = 0
        for shift in range(0, 35, 7):
            b = self.byte()
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                return result
        raise BlackboxDecodeError("variable-byte integer longer than 5 bytes")

    def svb(self) -> int:
        v = self.uvb()
        return (v >> 1) ^ -(v & 1)  # zig-zag decode

    def tag8_8svb(self, count: int) -> list[int]:
        if count == 1:
            return [self.svb()]
        header = self.byte()
        values = []
        for _ in range(count):
            values.append(self.svb() if header & 0x01 else 0)
            header >>= 1
        return values

    def _variable_3(self, selector: int) -> list[int]:
        values = []
        for _ in range(3):
            width = selector & 0x03
            if width == 0:
                values.append(_sign_extend(self.byte(), 8))
            elif width == 1:
                b1, b2 = self.byte(), self.byte()
                values.append(_sign_extend(b1 | (b2 << 8), 16))
            elif width == 2:
                b1, b2, b3 = self.byte(), self.byte(), self.byte()
                values.append(_sign_extend(b1 | (b2 << 8) | (b3 << 16), 24))
            else:
                b1, b2, b3, b4 = self.byte(), self.byte(), self.byte(), self.byte()
                values.append(_sign_extend(b1 | (b2 << 8) | (b3 << 16) | (b4 << 24), 32))
            selector >>= 2
        return values

    def tag2_3s32(self) -> list[int]:
        lead = self.byte()
        mode = lead >> 6
        if mode == 0:
            return [_sign_extend((lead >> 4) & 0x03, 2),
                    _sign_extend((lead >> 2) & 0x03, 2),
                    _sign_extend(lead & 0x03, 2)]
        if mode == 1:
            v0 = _sign_extend(lead & 0x0F, 4)
            b = self.byte()
            return [v0, _sign_extend(b >> 4, 4), _sign_extend(b & 0x0F, 4)]
        if mode == 2:
            v0 = _sign_extend(lead & 0x3F, 6)
            v1 = _sign_extend(self.byte() & 0x3F, 6)
            v2 = _sign_extend(self.byte() & 0x3F, 6)
            return [v0, v1, v2]
        return self._variable_3(lead)

    def tag2_3svariable(self) -> list[int]:
        lead = self.byte()
        mode = lead >> 6
        if mode == 0:
            return [_sign_extend((lead >> 4) & 0x03, 2),
                    _sign_extend((lead >> 2) & 0x03, 2),
                    _sign_extend(lead & 0x03, 2)]
        if mode == 1:
            b1 = self.byte()
            return [_sign_extend((lead & 0x3E) >> 1, 5),
                    _sign_extend(((lead & 0x01) << 4) | ((b1 & 0xF0) >> 4), 5),
                    _sign_extend(b1 & 0x0F, 4)]
        if mode == 2:
            b1, b2 = self.byte(), self.byte()
            return [_sign_extend(((lead & 0x3F) << 2) | ((b1 & 0xC0) >> 6), 8),
                    _sign_extend(((b1 & 0x3F) << 1) | ((b2 & 0x80) >> 7), 7),
                    _sign_extend(b2 & 0x7F, 7)]
        return self._variable_3(lead)

    def tag8_4s16(self) -> list[int]:
        """Data-version-2 layout of TAG8_4S16."""
        selector = self.byte()
        values = []
        nibble_pending = False
        buffer = 0
        for _ in range(4):
            kind = selector & 0x03
            if kind == 0:
                values.append(0)
            elif kind == 1:  # 4-bit
                if not nibble_pending:
                    buffer = self.byte()
                    values.append(_sign_extend(buffer >> 4, 4))
                    nibble_pending = True
                else:
                    values.append(_sign_extend(buffer & 0x0F, 4))
                    nibble_pending = False
            elif kind == 2:  # 8-bit
                if not nibble_pending:
                    values.append(_sign_extend(self.byte(), 8))
                else:
                    c1 = (buffer << 4) & 0xFF
                    buffer = self.byte()
                    c1 |= buffer >> 4
                    values.append(_sign_extend(c1, 8))
            else:  # 16-bit, big-endian in this encoding
                if not nibble_pending:
                    c1, c2 = self.byte(), self.byte()
                else:
                    c1 = (buffer << 4) & 0xFF
                    buffer = self.byte()
                    c1 |= buffer >> 4
                    c2 = (buffer << 4) & 0xFF
                    buffer = self.byte()
                    c2 |= buffer >> 4
                values.append(_sign_extend((c1 << 8) | c2, 16))
            selector >>= 2
        return values


# ------------------------------------------------------------ data classes
@dataclass
class FrameDef:
    names: list[str]
    signed: list[bool]
    predictors: list[int]
    encodings: list[int]

    def index(self, name: str) -> int | None:
        try:
            return self.names.index(name)
        except ValueError:
            return None


@dataclass
class DecodeStats:
    frames_accepted: dict[str, int] = field(default_factory=dict)
    frames_corrupt: dict[str, int] = field(default_factory=dict)
    p_frames_without_history: int = 0
    main_frames_implausible: int = 0
    gps_frames_without_home: int = 0
    bytes_skipped_resync: int = 0
    unknown_event_types: list[int] = field(default_factory=list)
    truncated_at_end: bool = False
    log_end_marker_found: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "frames_accepted": dict(self.frames_accepted),
            "frames_corrupt": dict(self.frames_corrupt),
            "p_frames_without_history": self.p_frames_without_history,
            "main_frames_implausible": self.main_frames_implausible,
            "gps_frames_without_home": self.gps_frames_without_home,
            "bytes_skipped_resync": self.bytes_skipped_resync,
            "unknown_event_types": sorted(set(self.unknown_event_types)),
            "truncated_at_end": self.truncated_at_end,
            "log_end_marker_found": self.log_end_marker_found,
        }


@dataclass
class BlackboxLog:
    index: int
    file_offset: int
    headers: dict[str, str]
    main_frames: list[dict[str, Any]] = field(default_factory=list)
    gps_frames: list[dict[str, Any]] = field(default_factory=list)
    home_frames: list[dict[str, Any]] = field(default_factory=list)
    slow_frames: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    stats: DecodeStats = field(default_factory=DecodeStats)


# ------------------------------------------------------------ header parse
def split_logs(data: bytes) -> list[tuple[int, bytes]]:
    """A single .bbl/.bfl file may contain several logs (one per arming)."""
    starts = []
    pos = data.find(LOG_START_MARKER)
    while pos != -1:
        starts.append(pos)
        pos = data.find(LOG_START_MARKER, pos + 1)
    out = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(data)
        out.append((start, data[start:end]))
    return out


def parse_headers(data: bytes) -> tuple[dict[str, str], int]:
    """Parse 'H key:value' lines. Returns (headers, offset of first frame)."""
    headers: dict[str, str] = {}
    pos = 0
    while pos < len(data) and data.startswith(b"H ", pos):
        nl = data.find(b"\n", pos)
        if nl == -1:
            break
        line = data[pos + 2:nl].decode("latin-1").rstrip("\r")
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key] = value
        pos = nl + 1
    return headers, pos


def _int_list(text: str | None) -> list[int]:
    if not text:
        return []
    return [int(x) for x in text.split(",") if x.strip() != ""]


def build_frame_defs(headers: dict[str, str]) -> dict[str, FrameDef]:
    defs: dict[str, FrameDef] = {}
    for ftype in ("I", "G", "H", "S"):
        names_raw = headers.get(f"Field {ftype} name")
        if not names_raw:
            continue
        names = names_raw.split(",")
        n = len(names)
        signed = [bool(v) for v in _int_list(headers.get(f"Field {ftype} signed"))] or [False] * n
        defs[ftype] = FrameDef(
            names=names,
            signed=(signed + [False] * n)[:n],
            predictors=(_int_list(headers.get(f"Field {ftype} predictor")) + [0] * n)[:n],
            encodings=(_int_list(headers.get(f"Field {ftype} encoding")) + [ENC_NULL] * n)[:n],
        )
    if "I" in defs and headers.get("Field P predictor"):
        i_def = defs["I"]
        n = len(i_def.names)
        defs["P"] = FrameDef(
            names=i_def.names,
            signed=i_def.signed,
            predictors=(_int_list(headers.get("Field P predictor")) + [0] * n)[:n],
            encodings=(_int_list(headers.get("Field P encoding")) + [ENC_NULL] * n)[:n],
        )
    return defs


# ---------------------------------------------------------------- decoder
class BlackboxLogDecoder:
    def __init__(self, raw: bytes, index: int = 0, file_offset: int = 0):
        self.raw = raw
        self.index = index
        self.file_offset = file_offset
        self.headers, self.frames_start = parse_headers(raw)
        self.defs = build_frame_defs(self.headers)

        self.i_interval = max(int(self.headers.get("I interval", "1") or 1), 1)
        self.p_num, self.p_denom = self._parse_p_interval(self.headers.get("P interval"))
        self.minthrottle = self._header_int("minthrottle", 0)
        self.vbatref = self._header_int("vbatref", 0)
        motor_output = _int_list(self.headers.get("motorOutput"))
        self.minmotor = motor_output[0] if motor_output else 0

        # decoder state
        self.prev: list[int] | None = None
        self.prev2: list[int] | None = None
        self.main_history_valid = False
        self.last_iteration: int | None = None
        self.last_main_time: int | None = None
        self.prev_gps: list[int] | None = None
        self.home: list[int] | None = None

    # -------------------------------------------------------- header utils
    def _header_int(self, key: str, default: int) -> int:
        try:
            return int(self.headers.get(key, default))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_p_interval(text: str | None) -> tuple[int, int]:
        if not text:
            return 1, 1
        try:
            if "/" in text:
                num, denom = text.split("/", 1)
                return max(int(num), 1), max(int(denom), 1)
            return 1, max(int(text), 1)
        except ValueError:
            return 1, 1

    def _should_have_frame(self, iteration: int) -> bool:
        return (iteration % self.i_interval + self.p_num - 1) % self.p_denom < self.p_num

    def _plausible(self, ftype: str, values: list[int]) -> bool:
        names = self.defs[ftype].names
        if "time" in names and self.last_main_time is not None:
            dt = values[names.index("time")] - self.last_main_time
            if dt < 0 or dt > MAX_TIME_JUMP_US:
                return False
        if "loopIteration" in names and self.last_iteration is not None:
            di = values[names.index("loopIteration")] - self.last_iteration
            if di < 0 or di > MAX_ITERATION_JUMP:
                return False
        return True

    def _skipped_frames(self) -> int:
        if self.last_iteration is None:
            return 0
        skipped = 0
        it = self.last_iteration + 1
        while not self._should_have_frame(it) and skipped < 10_000:
            skipped += 1
            it += 1
        return skipped

    # ------------------------------------------------------ field decoding
    def _decode_fields(self, reader: _Reader, fdef: FrameDef, ftype: str,
                       previous: list[int] | None, previous2: list[int] | None) -> list[int]:
        n = len(fdef.names)
        current = [0] * n
        i = 0
        while i < n:
            pred = fdef.predictors[i]
            if pred == PRED_INC:
                current[i] = self._skipped_frames() + 1 + (previous[i] if previous else 0)
                i += 1
                continue

            enc = fdef.encodings[i]
            if enc == ENC_SIGNED_VB:
                raw = [reader.svb()]
            elif enc == ENC_UNSIGNED_VB:
                raw = [reader.uvb()]
            elif enc == ENC_NEG_14BIT:
                raw = [-_sign_extend(reader.uvb(), 14)]
            elif enc == ENC_TAG8_8SVB:
                count = 1
                while i + count < n and count < 8 and fdef.encodings[i + count] == ENC_TAG8_8SVB:
                    count += 1
                raw = reader.tag8_8svb(count)
            elif enc == ENC_TAG2_3S32:
                raw = reader.tag2_3s32()
            elif enc == ENC_TAG2_3SVARIABLE:
                raw = reader.tag2_3svariable()
            elif enc == ENC_TAG8_4S16:
                raw = reader.tag8_4s16()
            elif enc == ENC_NULL:
                raw = [0]
            else:
                raise BlackboxDecodeError(f"unsupported encoding {enc} for field {fdef.names[i]}")

            for k, value in enumerate(raw):
                j = i + k
                if j >= n:
                    break
                current[j] = self._apply_predictor(j, value, fdef, ftype, current, previous, previous2)
            i += len(raw)
        return current

    def _apply_predictor(self, j: int, value: int, fdef: FrameDef, ftype: str,
                         current: list[int], previous: list[int] | None,
                         previous2: list[int] | None) -> int:
        pred = fdef.predictors[j]
        if pred == PRED_ZERO:
            pass
        elif pred == PRED_PREVIOUS:
            value += previous[j] if previous else 0
        elif pred == PRED_STRAIGHT_LINE:
            if previous:
                p2 = previous2 if previous2 else previous
                value += 2 * previous[j] - p2[j]
        elif pred == PRED_AVERAGE_2:
            if previous:
                p2 = previous2 if previous2 else previous
                value += _trunc_div2(previous[j] + p2[j])
        elif pred == PRED_MINTHROTTLE:
            value += self.minthrottle
        elif pred == PRED_MOTOR_0:
            m0 = fdef.index("motor[0]")
            if m0 is None:
                raise BlackboxDecodeError("MOTOR_0 predictor without motor[0] field")
            value += current[m0]
        elif pred == PRED_HOME_COORD:
            if self.home is None:
                raise _NoHome()
            value += self.home[1 if fdef.names[j].endswith("[1]") else 0]
        elif pred == PRED_1500:
            value += 1500
        elif pred == PRED_VBATREF:
            value += self.vbatref
        elif pred == PRED_LAST_MAIN_FRAME_TIME:
            value += self.last_main_time or 0
        elif pred == PRED_MINMOTOR:
            value += self.minmotor
        else:
            raise BlackboxDecodeError(f"unsupported predictor {pred} for field {fdef.names[j]}")
        return _wrap32(value, fdef.signed[j])

    # ---------------------------------------------------------- frame types
    def _event(self, reader: _Reader) -> dict[str, Any]:
        etype = reader.byte()
        event: dict[str, Any] = {"event_type": etype, "event_name": EVENT_NAMES.get(etype)}
        if etype == EVENT_SYNC_BEEP:
            event["time_us"] = reader.uvb()
        elif etype == EVENT_INFLIGHT_ADJUSTMENT:
            func = reader.byte()
            event["adjustment_function"] = func & 0x7F
            if func & 0x80:
                event["new_value"] = struct.unpack("<f", bytes(reader.byte() for _ in range(4)))[0]
            else:
                event["new_value"] = reader.svb()
        elif etype == EVENT_LOGGING_RESUME:
            event["log_iteration"] = reader.uvb()
            event["current_time_us"] = reader.uvb()
        elif etype == EVENT_DISARM:
            event["reason"] = reader.uvb()
        elif etype == EVENT_FLIGHT_MODE:
            event["flags"] = reader.uvb()
            event["last_flags"] = reader.uvb()
        elif etype == EVENT_LOG_END:
            end = b"End of log\x00"
            got = bytes(reader.byte() for _ in range(len(end)))
            if got != end:
                raise BlackboxDecodeError("malformed LOG_END event")
        else:
            raise _UnknownEvent(etype)
        return event

    def decode(self) -> BlackboxLog:
        log = BlackboxLog(index=self.index, file_offset=self.file_offset, headers=dict(self.headers))
        stats = log.stats
        data = self.raw
        pos = self.frames_start
        n = len(data)

        def bump(bucket: dict[str, int], key: str) -> None:
            bucket[key] = bucket.get(key, 0) + 1

        while pos < n:
            marker = data[pos]
            ftype = chr(marker)
            if marker not in FRAME_MARKERS or (ftype != "E" and ftype not in self.defs):
                stats.bytes_skipped_resync += 1
                pos += 1
                continue

            reader = _Reader(data, pos + 1)
            frame_offset = self.file_offset + pos
            try:
                if ftype in ("I", "P"):
                    if ftype == "P" and not self.main_history_valid:
                        stats.p_frames_without_history += 1
                        # Still need to consume it to find the next frame;
                        # decode against no history, then discard.
                        self._decode_fields(reader, self.defs["P"], "P", None, None)
                        values = None
                    elif ftype == "I":
                        values = self._decode_fields(reader, self.defs["I"], "I", self.prev, self.prev2)
                    else:
                        values = self._decode_fields(reader, self.defs["P"], "P", self.prev, self.prev2)
                elif ftype == "G":
                    try:
                        values = self._decode_fields(reader, self.defs["G"], "G", self.prev_gps, None)
                    except _NoHome:
                        # consume the frame with a zero home so the stream stays aligned
                        self.home, saved = [0, 0], self.home
                        reader = _Reader(data, pos + 1)
                        self._decode_fields(reader, self.defs["G"], "G", self.prev_gps, None)
                        self.home = saved
                        values = None
                        stats.gps_frames_without_home += 1
                elif ftype == "H":
                    values = self._decode_fields(reader, self.defs["H"], "H", None, None)
                elif ftype == "S":
                    values = self._decode_fields(reader, self.defs["S"], "S", None, None)
                else:
                    values = self._event(reader)
            except _UnknownEvent as exc:
                stats.unknown_event_types.append(exc.etype)
                bump(stats.frames_corrupt, ftype)
                self.main_history_valid = False
                pos += 1
                continue
            except BlackboxDecodeError:
                if reader.pos >= n:
                    stats.truncated_at_end = True
                    break
                bump(stats.frames_corrupt, ftype)
                self.main_history_valid = False
                pos += 1
                continue

            end = reader.pos
            # Validation: the next byte must start a frame, or we must be at EOF.
            if end < n and data[end] not in FRAME_MARKERS:
                bump(stats.frames_corrupt, ftype)
                if ftype in ("I", "P"):
                    self.main_history_valid = False
                pos += 1
                continue

            # Plausibility: time/iteration must move forward by a sane amount.
            if ftype in ("I", "P") and values is not None and not self._plausible(ftype, values):
                stats.main_frames_implausible += 1
                self.main_history_valid = False
                pos = end
                continue

            # ---------------- accept frame
            if ftype in ("I", "P") and values is not None:
                names = self.defs[ftype].names
                frame = dict(zip(names, values))
                frame["_frame_type"] = ftype
                frame["_file_offset"] = frame_offset
                log.main_frames.append(frame)
                self.prev2 = self.prev if ftype == "P" else values
                self.prev = values
                self.main_history_valid = True
                if "loopIteration" in frame:
                    self.last_iteration = frame["loopIteration"]
                if "time" in frame:
                    self.last_main_time = frame["time"]
                bump(stats.frames_accepted, ftype)
            elif ftype == "G" and values is not None:
                frame = dict(zip(self.defs["G"].names, values))
                frame["_file_offset"] = frame_offset
                frame["_last_main_time"] = self.last_main_time
                log.gps_frames.append(frame)
                self.prev_gps = values
                bump(stats.frames_accepted, ftype)
            elif ftype == "H":
                frame = dict(zip(self.defs["H"].names, values))
                frame["_file_offset"] = frame_offset
                frame["_last_main_time"] = self.last_main_time
                log.home_frames.append(frame)
                self.home = [frame.get("GPS_home[0]", 0), frame.get("GPS_home[1]", 0)]
                bump(stats.frames_accepted, ftype)
            elif ftype == "S":
                frame = dict(zip(self.defs["S"].names, values))
                frame["_file_offset"] = frame_offset
                frame["_last_main_time"] = self.last_main_time
                log.slow_frames.append(frame)
                bump(stats.frames_accepted, ftype)
            elif ftype == "E":
                values["_file_offset"] = frame_offset
                values["_last_main_time"] = self.last_main_time
                log.events.append(values)
                bump(stats.frames_accepted, ftype)
                if values["event_type"] == EVENT_LOGGING_RESUME:
                    self.last_iteration = values["log_iteration"]
                    self.last_main_time = values["current_time_us"]
                    self.main_history_valid = False
                if values["event_type"] == EVENT_LOG_END:
                    stats.log_end_marker_found = True
                    break
            pos = end
        return log


class _NoHome(BlackboxDecodeError):
    pass


class _UnknownEvent(BlackboxDecodeError):
    def __init__(self, etype: int):
        super().__init__(f"unknown event type {etype}")
        self.etype = etype


def decode_bytes(data: bytes) -> list[BlackboxLog]:
    return [BlackboxLogDecoder(chunk, index=i, file_offset=offset).decode()
            for i, (offset, chunk) in enumerate(split_logs(data))]


def decode_file(path: str) -> list[BlackboxLog]:
    with open(path, "rb") as fh:
        return decode_bytes(fh.read())
