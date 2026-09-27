"""
Create a synthetic EmuFlight Blackbox log with known ground truth.

The file exercises every encoding and predictor the parser supports:
I/P main frames, TAG2_3S32, TAG8_4S16, TAG8_8SVB, NEG_14BIT, NULL,
straight-line / average-2 / increment / motor-0 / min-motor / vbatref /
home-coordinate / last-main-frame-time predictors, slow frames, GPS and
home frames, events, and two logs in one file.

IMPORTANT: this fixture is written by an encoder built from the same
understanding of the format as the decoder, so passing tests prove
internal consistency, not agreement with real EmuFlight firmware. See
the README for validation against a real log.

Run from the project root:
    python tests/fixtures/create_emuflight_fixture.py
"""

from __future__ import annotations

import struct
from pathlib import Path

OUTPUT = Path("tests/fixtures/synthetic_emuflight.bbl")

MINMOTOR = 1070
VBATREF = 420
HOME = (473979450, 85461760)  # degrees x 1e7


# ------------------------------------------------------------ primitive writers
def uvb(value: int) -> bytes:
    value &= 0xFFFFFFFF
    out = bytearray()
    while value > 127:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def svb(value: int) -> bytes:
    return uvb((value << 1) ^ (value >> 31))


def tag8_8svb(values: list[int]) -> bytes:
    if len(values) == 1:
        return svb(values[0])
    header = 0
    body = b""
    for i, v in enumerate(values):
        if v != 0:
            header |= 1 << i
            body += svb(v)
    return bytes([header]) + body


def tag2_3s32(values: list[int]) -> bytes:
    if all(-2 <= v <= 1 for v in values):
        return bytes([(0 << 6) | ((values[0] & 3) << 4) | ((values[1] & 3) << 2) | (values[2] & 3)])
    if all(-8 <= v <= 7 for v in values):
        return bytes([(1 << 6) | (values[0] & 0x0F), ((values[1] & 0x0F) << 4) | (values[2] & 0x0F)])
    if all(-32 <= v <= 31 for v in values):
        return bytes([(2 << 6) | (values[0] & 0x3F), values[1] & 0x3F, values[2] & 0x3F])
    selector = 0
    body = b""
    for i, v in enumerate(values):
        if -128 <= v <= 127:
            width, raw = 0, struct.pack("<b", v)
        elif -32768 <= v <= 32767:
            width, raw = 1, struct.pack("<h", v)
        elif -(1 << 23) <= v < (1 << 23):
            width, raw = 2, struct.pack("<i", v)[:3]
        else:
            width, raw = 3, struct.pack("<i", v)
        selector |= width << (i * 2)
        body += raw
    return bytes([(3 << 6) | selector]) + body


def tag8_4s16(values: list[int]) -> bytes:
    selector = 0
    for x, v in enumerate(values):
        if v == 0:
            kind = 0
        elif -8 <= v < 8:
            kind = 1
        elif -128 <= v < 128:
            kind = 2
        else:
            kind = 3
        selector |= kind << (x * 2)
    out = bytearray([selector])
    nibble = False
    buffer = 0
    sel = selector
    for v in values:
        kind = sel & 3
        if kind == 1:
            if not nibble:
                buffer = (v << 4) & 0xFF
                nibble = True
            else:
                out.append(buffer | (v & 0x0F))
                nibble = False
        elif kind == 2:
            if not nibble:
                out.append(v & 0xFF)
            else:
                out.append(buffer | ((v >> 4) & 0x0F))
                buffer = (v << 4) & 0xFF
        elif kind == 3:
            if not nibble:
                out += bytes([(v >> 8) & 0xFF, v & 0xFF])
            else:
                out.append(buffer | ((v >> 12) & 0x0F))
                out.append((v >> 4) & 0xFF)
                buffer = (v << 4) & 0xFF
        sel >>= 2
    if nibble:
        out.append(buffer)
    return bytes(out)


def trunc_div2(v: int) -> int:
    q = abs(v) // 2
    return q if v >= 0 else -q


# ------------------------------------------------------------------ headers
I_FIELDS = ["loopIteration", "time", "axisP[0]", "axisP[1]", "axisP[2]",
            "rcCommand[0]", "rcCommand[1]", "rcCommand[2]", "rcCommand[3]",
            "vbatLatest", "motor[0]", "motor[1]", "motor[2]", "motor[3]"]


def header_block(revision: str) -> bytes:
    lines = [
        "Product:Blackbox flight data recorder by Nicholas Sherlock",
        "Data version:2",
        "I interval:32",
        "P interval:1/1",
        "Field I name:" + ",".join(I_FIELDS),
        "Field I signed:0,0,1,1,1,1,1,1,0,0,0,0,0,0",
        "Field I predictor:0,0,0,0,0,0,0,0,0,9,11,5,5,5",
        "Field I encoding:1,1,0,0,0,0,0,0,1,3,1,0,0,0",
        "Field P predictor:6,2,1,1,1,1,1,1,1,1,3,3,3,3",
        "Field P encoding:9,0,7,7,7,8,8,8,8,6,6,6,6,6",
        "Field S name:flightModeFlags,stateFlags,failsafePhase,rxSignalReceived,rxFlightChannelsValid",
        "Field S signed:0,0,0,0,0",
        "Field S predictor:0,0,0,0,0",
        "Field S encoding:1,1,1,1,1",
        "Field G name:time,GPS_numSat,GPS_coord[0],GPS_coord[1],GPS_altitude,GPS_speed,GPS_ground_course",
        "Field G signed:0,0,1,1,0,0,0",
        "Field G predictor:10,0,7,7,0,0,0",
        "Field G encoding:1,1,0,0,1,1,1",
        "Field H name:GPS_home[0],GPS_home[1]",
        "Field H signed:1,1",
        "Field H predictor:0,0",
        "Field H encoding:0,0",
        "Firmware type:Cleanflight",
        f"Firmware revision:{revision}",
        "Board information:TEST STM32F7X2",
        "Log start datetime:2026-09-27T10:00:00.000+00:00",
        "Craft name:TESTQUAD",
        f"minthrottle:{MINMOTOR}",
        f"vbatref:{VBATREF}",
        f"motorOutput:{MINMOTOR},2000",
        "rates:70,70,70",
    ]
    return b"".join(b"H " + line.encode() + b"\n" for line in lines)


# ------------------------------------------------------------------- frames
def encode_i(v: list[int]) -> bytes:
    out = b"I" + uvb(v[0]) + uvb(v[1])
    out += b"".join(svb(x) for x in v[2:8])
    out += uvb(v[8])
    out += uvb((VBATREF - v[9]) & 0x3FFF)
    out += uvb(v[10] - MINMOTOR)
    out += b"".join(svb(v[k] - v[10]) for k in (11, 12, 13))
    return out


def encode_p(v: list[int], prev: list[int], prev2: list[int]) -> bytes:
    out = b"P"
    out += svb(v[1] - (2 * prev[1] - prev2[1]))
    out += tag2_3s32([v[k] - prev[k] for k in (2, 3, 4)])
    out += tag8_4s16([v[k] - prev[k] for k in (5, 6, 7, 8)])
    deltas = [v[9] - prev[9]] + [v[k] - trunc_div2(prev[k] + prev2[k]) for k in (10, 11, 12, 13)]
    out += tag8_8svb(deltas)
    return out


def build_log(revision: str, iterations: int, t0_us: int, seed: int, with_gps: bool):
    truth = {"main": [], "gps": [], "slow": [], "events": []}
    body = bytearray(header_block(revision))
    prev = prev2 = None
    t = t0_us
    last_main_time = None
    home_written = False
    state = [0x1, 0x3, 0, 1, 1]

    for it in range(iterations):
        t += 1000 + ((it * 7 + seed) % 5) - 2  # ~1 kHz with small jitter
        phase = it / 20.0
        v = [
            it, t,
            int(40 * (1 if it % 40 < 20 else -1)) + it % 7,
            -3 + it % 5, 900 + it * 3,                      # large values -> wider encodings
            (it % 9) - 4, 60 - (it % 3), -(it * 5 % 300), 1300 + it % 11,
            410 - it // 50,
            1400 + (it * 13) % 300, 1410 + (it * 11) % 290,
            1395 + (it * 17) % 310, 1405 + (it * 19) % 280,
        ]
        if it % 32 == 0:
            body += encode_i(v)
            prev = prev2 = v
        else:
            body += encode_p(v, prev, prev2)
            prev2, prev = prev, v
        last_main_time = t
        truth["main"].append(dict(zip(I_FIELDS, v)))

        if it == 0 or it == 100 or it == 120 or it == 150:
            if it == 100:
                state = [0x1, 0x3, 1, 0, 0]   # RX loss
            elif it == 120:
                state = [0x1, 0x3, 0, 1, 1]   # recovered
            elif it == 150:
                state = [0x1, 0x3, 0, 1, 1]   # identical: must be de-duplicated
            body += b"S" + b"".join(uvb(x) for x in state)
            truth["slow"].append({"time": last_main_time, "state": list(state)})

        if with_gps:
            if it == 5:
                # GPS frame BEFORE any home frame: must be rejected, not mis-decoded
                body += b"G" + uvb(0) + uvb(4) + svb(10) + svb(10) + uvb(0) + uvb(0) + uvb(0)
            if it == 9 and not home_written:
                body += b"H" + svb(HOME[0]) + svb(HOME[1])
                home_written = True
            if home_written and it % 10 == 0:
                lat = HOME[0] + it * 3
                lon = HOME[1] - it * 2
                g = {"time": t + 150, "GPS_numSat": 9 + it % 3, "GPS_coord[0]": lat,
                     "GPS_coord[1]": lon, "GPS_altitude": 1234, "GPS_speed": 250 + it,
                     "GPS_ground_course": 1800 + it}
                body += (b"G" + uvb(g["time"] - last_main_time) + uvb(g["GPS_numSat"])
                         + svb(lat - HOME[0]) + svb(lon - HOME[1])
                         + uvb(g["GPS_altitude"]) + uvb(g["GPS_speed"]) + uvb(g["GPS_ground_course"]))
                truth["gps"].append(g)

        if it == 50:
            body += b"E" + bytes([30]) + uvb(0x5) + uvb(0x1)       # FLIGHT_MODE
            truth["events"].append(("FLIGHT_MODE", last_main_time))
        if it == 60:
            body += b"E" + bytes([13]) + bytes([0x80 | 3]) + struct.pack("<f", 0.5)
            truth["events"].append(("INFLIGHT_ADJUSTMENT", last_main_time))

    body += b"E" + bytes([15]) + uvb(4)                           # DISARM, reason 4
    truth["events"].append(("DISARM", last_main_time))
    body += b"E" + bytes([255]) + b"End of log\x00"
    truth["events"].append(("LOG_END", last_main_time))
    return bytes(body), truth


REVISION = "EmuFlight 0.4.1 (1a2b3c4) STM32F7X2"


def build_fixture():
    log0, truth0 = build_log(REVISION, iterations=200, t0_us=5_000_000, seed=1, with_gps=True)
    log1, truth1 = build_log(REVISION, iterations=40, t0_us=90_000_000, seed=3, with_gps=False)
    return log0 + log1, [truth0, truth1], len(log0)


def main() -> None:
    data, truths, _ = build_fixture()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(data)
    print(f"Wrote {OUTPUT} ({len(data)} bytes)")
    for i, t in enumerate(truths):
        print(f"  log {i}: {len(t['main'])} main frames, {len(t['gps'])} GPS frames, "
              f"{len(t['slow'])} slow frames, {len(t['events'])} events")


if __name__ == "__main__":
    main()
