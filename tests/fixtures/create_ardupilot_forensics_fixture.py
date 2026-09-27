#!/usr/bin/env python3

"""
Create a synthetic ArduPilot DataFlash forensic fixture.

This fixture is designed to test the multi-platform forensic
parser without modifying the existing PX4 forensic files.

It contains:

    GPS   x2
    POS   x2
    BAT   x2
    PARM  x1
    MODE  x1
    ARM   x1
    EV    x1
    ERR   x1
    MAVC  x1

The fixture follows the ArduPilot DataFlash packet structure:

    A3 95 <message_type> <payload>

and includes FMT records describing the message schemas.

IMPORTANT
---------
ArduPilot DataFlash format characters are NOT identical to
Python's struct format characters.

In particular:

    ArduPilot 'c' = int16_t
    ArduPilot 'e' = int32_t
    ArduPilot 'L' = int32_t

Therefore Python struct formats are explicitly defined
separately from the ArduPilot format strings.
"""

from pathlib import Path
import struct


# ============================================================
# CONSTANTS
# ============================================================

HEADER = b"\xA3\x95"

FMT_MESSAGE_ID = 128
FMT_RECORD_LENGTH = 89


# ============================================================
# GENERIC HELPERS
# ============================================================

def fixed_string(value, size):
    """
    Encode an ASCII string into a fixed-size null-padded field.
    """

    data = value.encode("ascii")

    if len(data) > size:
        raise ValueError(
            f"String {value!r} is too long for {size} bytes"
        )

    return data.ljust(size, b"\x00")


def make_fmt_record(
    message_type,
    message_length,
    name,
    fmt,
    labels,
):
    """
    Construct an ArduPilot FMT record.

    FMT structure:

        Header       3 bytes
        Type         1 byte
        Length       1 byte
        Name         4 bytes
        Format      16 bytes
        Labels      64 bytes

    Total:

        3 + 1 + 1 + 4 + 16 + 64 = 89 bytes
    """

    record = (
        HEADER
        + bytes([FMT_MESSAGE_ID])
        + struct.pack(
            "<BB",
            message_type,
            message_length,
        )
        + fixed_string(name, 4)
        + fixed_string(fmt, 16)
        + fixed_string(labels, 64)
    )

    if len(record) != FMT_RECORD_LENGTH:
        raise ValueError(
            "FMT record size mismatch: "
            f"{len(record)} != {FMT_RECORD_LENGTH}"
        )

    return record


def make_data_record(message_type, payload):
    """
    Construct a normal DataFlash record.

    DataFlash packet header:

        A3 95 <message_type>
    """

    return (
        HEADER
        + bytes([message_type])
        + payload
    )


# ============================================================
# GPS
# ============================================================

"""
ArduPilot GPS format:

    QBBIHBcLLeffffB

Fields:

    TimeUS
    I
    Status
    GMS
    GWk
    NSats
    HDop
    Lat
    Lng
    Alt
    Spd
    GCrs
    VZ
    Yaw
    U

ArduPilot format sizes:

    Q = uint64       8 bytes
    B = uint8        1 byte
    B = uint8        1 byte
    I = uint32       4 bytes
    H = uint16       2 bytes
    B = uint8        1 byte
    c = int16        2 bytes
    L = int32        4 bytes
    L = int32        4 bytes
    e = int32        4 bytes
    f = float        4 bytes
    f = float        4 bytes
    f = float        4 bytes
    f = float        4 bytes
    B = uint8        1 byte

Total payload = 48 bytes.

DataFlash header = 3 bytes.

Therefore:

    GPS record length = 51 bytes

Python-compatible byte layout:

    QBBIHBhiiiffffB

The Python 'h' is used for ArduPilot 'c'
because both occupy 2 bytes.
"""

GPS_FMT = "QBBIHBcLLeffffB"

GPS_LABELS = (
    "TimeUS,I,Status,GMS,GWk,NSats,HDop,"
    "Lat,Lng,Alt,Spd,GCrs,VZ,Yaw,U"
)

GPS_PYTHON_FMT = "<QBBIHBhiiiffffB"

GPS_PAYLOAD_SIZE = struct.calcsize(
    GPS_PYTHON_FMT
)

GPS_MESSAGE_LENGTH = (
    3 + GPS_PAYLOAD_SIZE
)


# ============================================================
# POS
# ============================================================

"""
ArduPilot POS format:

    QLLfff

Fields:

    TimeUS
    Lat
    Lng
    Alt
    RelHomeAlt
    RelOriginAlt

ArduPilot format:

    Q = uint64
    L = int32 latitude/longitude
    f = float

Lat/Lng are stored as degrees * 1e7.
Altitude fields are stored directly as meters.
"""

POS_FMT = "QLLfff"

POS_LABELS = (
    "TimeUS,Lat,Lng,Alt,RelHomeAlt,RelOriginAlt"
)

POS_PYTHON_FMT = "<QLLfff"

POS_PAYLOAD_SIZE = struct.calcsize(
    POS_PYTHON_FMT
)

POS_MESSAGE_LENGTH = (
    3 + POS_PAYLOAD_SIZE
)


# ============================================================
# BATTERY
# ============================================================

"""
Synthetic ArduPilot BAT record.

Fields:

    TimeUS
    Inst
    Volt
    VoltR
    Curr
    CurrTot
    EnrgTot
    Temp
    Res
    RemPct
    H
    SH

Meaning:

    TimeUS  = timestamp in microseconds
    Inst    = battery instance
    Volt    = battery voltage
    VoltR   = resistance-compensated/resting voltage
    Curr    = current
    CurrTot = consumed current/charge quantity
    EnrgTot = consumed energy
    Temp    = temperature
    Res     = internal resistance
    RemPct  = remaining battery percentage
    H       = battery health
    SH      = state of health

IMPORTANT:

ArduPilot's 'c' DataFlash format is an int16 field.
The parser handles the DataFlash scaling for this field.

Python therefore uses 'h' for the Temp field.
"""

BAT_FMT = "QBfffffcfBBB"

BAT_LABELS = (
    "TimeUS,Inst,Volt,VoltR,Curr,CurrTot,"
    "EnrgTot,Temp,Res,RemPct,H,SH"
)

BAT_PYTHON_FMT = "<QBfffffhfBBB"

BAT_PAYLOAD_SIZE = struct.calcsize(
    BAT_PYTHON_FMT
)

BAT_MESSAGE_LENGTH = (
    3 + BAT_PAYLOAD_SIZE
)


# ============================================================
# PARM
# ============================================================

"""
Synthetic PARM record.

Format:

    QNff

Fields:

    TimeUS
    Name
    Value
    Default
"""

PARM_FMT = "QNff"

PARM_LABELS = (
    "TimeUS,Name,Value,Default"
)

PARM_PYTHON_FMT = "<Q16sff"

PARM_PAYLOAD_SIZE = struct.calcsize(
    PARM_PYTHON_FMT
)

PARM_MESSAGE_LENGTH = (
    3 + PARM_PAYLOAD_SIZE
)


# ============================================================
# MODE
# ============================================================

MODE_FMT = "QBBB"

MODE_LABELS = (
    "TimeUS,Mode,ModeNum,Rsn"
)

MODE_PYTHON_FMT = "<QBBB"

MODE_PAYLOAD_SIZE = struct.calcsize(
    MODE_PYTHON_FMT
)

MODE_MESSAGE_LENGTH = (
    3 + MODE_PAYLOAD_SIZE
)


# ============================================================
# ARM
# ============================================================

ARM_FMT = "QBIBB"

ARM_LABELS = (
    "TimeUS,ArmState,ArmChecks,Forced,Method"
)

ARM_PYTHON_FMT = "<QBIBB"

ARM_PAYLOAD_SIZE = struct.calcsize(
    ARM_PYTHON_FMT
)

ARM_MESSAGE_LENGTH = (
    3 + ARM_PAYLOAD_SIZE
)


# ============================================================
# EV
# ============================================================

EV_FMT = "QB"

EV_LABELS = (
    "TimeUS,Id"
)

EV_PYTHON_FMT = "<QB"

EV_PAYLOAD_SIZE = struct.calcsize(
    EV_PYTHON_FMT
)

EV_MESSAGE_LENGTH = (
    3 + EV_PAYLOAD_SIZE
)


# ============================================================
# ERR
# ============================================================

ERR_FMT = "QBB"

ERR_LABELS = (
    "TimeUS,Subsys,ECode"
)

ERR_PYTHON_FMT = "<QBB"

ERR_PAYLOAD_SIZE = struct.calcsize(
    ERR_PYTHON_FMT
)

ERR_MESSAGE_LENGTH = (
    3 + ERR_PAYLOAD_SIZE
)


# ============================================================
# MAVC
# ============================================================

"""
MAVC command record.

Fields:

    TimeUS
    TS
    TC
    SS
    SC
    Fr
    Cmd
    P1
    P2
    P3
    P4
    X
    Y
    Z
    Res
    WL

ArduPilot format:

    QBBBBBHffffiifBB

Important:

    Q
    B TS
    B TC
    B SS
    B SC
    B Fr
    H Cmd

Therefore the command ID is the H field after
the five B fields.

Python format is byte-compatible:

    <QBBBBBHffffiifBB
"""

MAVC_FMT = (
    "QBBBBBHffffiifBB"
)

MAVC_LABELS = (
    "TimeUS,TS,TC,SS,SC,Fr,Cmd,"
    "P1,P2,P3,P4,X,Y,Z,Res,WL"
)

MAVC_PYTHON_FMT = (
    "<QBBBBBHffffiifBB"
)

MAVC_PAYLOAD_SIZE = struct.calcsize(
    MAVC_PYTHON_FMT
)

MAVC_MESSAGE_LENGTH = (
    3 + MAVC_PAYLOAD_SIZE
)


# ============================================================
# STRUCTURE VALIDATION
# ============================================================

def validate_structure_sizes():
    """
    Verify that all synthetic schemas have the expected
    packet sizes.

    This prevents silent fixture corruption.
    """

    # --------------------------------------------------------
    # POS
    # --------------------------------------------------------

    if POS_PAYLOAD_SIZE != 28:
        raise RuntimeError(
            "Unexpected POS payload size: "
            f"{POS_PAYLOAD_SIZE}, expected 28"
        )

    if POS_MESSAGE_LENGTH != 31:
        raise RuntimeError(
            "Unexpected POS message length: "
            f"{POS_MESSAGE_LENGTH}, expected 31"
        )

    # --------------------------------------------------------
    # GPS
    # --------------------------------------------------------

    if GPS_PAYLOAD_SIZE != 48:
        raise RuntimeError(
            "Unexpected GPS payload size: "
            f"{GPS_PAYLOAD_SIZE}, expected 48"
        )

    if GPS_MESSAGE_LENGTH != 51:
        raise RuntimeError(
            "Unexpected GPS message length: "
            f"{GPS_MESSAGE_LENGTH}, expected 51"
        )

    # --------------------------------------------------------
    # BAT
    # --------------------------------------------------------

    if BAT_PAYLOAD_SIZE != 38:
        raise RuntimeError(
            "Unexpected BAT payload size: "
            f"{BAT_PAYLOAD_SIZE}, expected 38"
        )

    if BAT_MESSAGE_LENGTH != 41:
        raise RuntimeError(
            "Unexpected BAT message length: "
            f"{BAT_MESSAGE_LENGTH}, expected 41"
        )

    # --------------------------------------------------------
    # PARM
    # --------------------------------------------------------

    if PARM_PAYLOAD_SIZE != 32:
        raise RuntimeError(
            "Unexpected PARM payload size: "
            f"{PARM_PAYLOAD_SIZE}, expected 32"
        )

    if PARM_MESSAGE_LENGTH != 35:
        raise RuntimeError(
            "Unexpected PARM message length: "
            f"{PARM_MESSAGE_LENGTH}, expected 35"
        )

    # --------------------------------------------------------
    # MODE
    # --------------------------------------------------------

    if MODE_PAYLOAD_SIZE != 11:
        raise RuntimeError(
            "Unexpected MODE payload size: "
            f"{MODE_PAYLOAD_SIZE}, expected 11"
        )

    if MODE_MESSAGE_LENGTH != 14:
        raise RuntimeError(
            "Unexpected MODE message length: "
            f"{MODE_MESSAGE_LENGTH}, expected 14"
        )

    # --------------------------------------------------------
    # ARM
    # --------------------------------------------------------

    if ARM_PAYLOAD_SIZE != 15:
        raise RuntimeError(
            "Unexpected ARM payload size: "
            f"{ARM_PAYLOAD_SIZE}, expected 15"
        )

    if ARM_MESSAGE_LENGTH != 18:
        raise RuntimeError(
            "Unexpected ARM message length: "
            f"{ARM_MESSAGE_LENGTH}, expected 18"
        )

    # --------------------------------------------------------
    # EV
    # --------------------------------------------------------

    if EV_PAYLOAD_SIZE != 9:
        raise RuntimeError(
            "Unexpected EV payload size: "
            f"{EV_PAYLOAD_SIZE}, expected 9"
        )

    if EV_MESSAGE_LENGTH != 12:
        raise RuntimeError(
            "Unexpected EV message length: "
            f"{EV_MESSAGE_LENGTH}, expected 12"
        )

    # --------------------------------------------------------
    # ERR
    # --------------------------------------------------------

    if ERR_PAYLOAD_SIZE != 10:
        raise RuntimeError(
            "Unexpected ERR payload size: "
            f"{ERR_PAYLOAD_SIZE}, expected 10"
        )

    if ERR_MESSAGE_LENGTH != 13:
        raise RuntimeError(
            "Unexpected ERR message length: "
            f"{ERR_MESSAGE_LENGTH}, expected 13"
        )

    # --------------------------------------------------------
    # MAVC
    # --------------------------------------------------------

    if MAVC_PAYLOAD_SIZE != 45:
        raise RuntimeError(
            "Unexpected MAVC payload size: "
            f"{MAVC_PAYLOAD_SIZE}, expected 45"
        )

    if MAVC_MESSAGE_LENGTH != 48:
        raise RuntimeError(
            "Unexpected MAVC message length: "
            f"{MAVC_MESSAGE_LENGTH}, expected 48"
        )


# ============================================================
# BUILD FMT RECORDS
# ============================================================

def build_fmt_records():
    """
    Create all FMT records.
    """

    return [
        make_fmt_record(
            message_type=1,
            message_length=GPS_MESSAGE_LENGTH,
            name="GPS",
            fmt=GPS_FMT,
            labels=GPS_LABELS,
        ),

        make_fmt_record(
            message_type=8,
            message_length=POS_MESSAGE_LENGTH,
            name="POS",
            fmt=POS_FMT,
            labels=POS_LABELS,
        ),

        make_fmt_record(
            message_type=9,
            message_length=BAT_MESSAGE_LENGTH,
            name="BAT",
            fmt=BAT_FMT,
            labels=BAT_LABELS,
        ),

        make_fmt_record(
            message_type=2,
            message_length=PARM_MESSAGE_LENGTH,
            name="PARM",
            fmt=PARM_FMT,
            labels=PARM_LABELS,
        ),

        make_fmt_record(
            message_type=3,
            message_length=MODE_MESSAGE_LENGTH,
            name="MODE",
            fmt=MODE_FMT,
            labels=MODE_LABELS,
        ),

        make_fmt_record(
            message_type=4,
            message_length=ARM_MESSAGE_LENGTH,
            name="ARM",
            fmt=ARM_FMT,
            labels=ARM_LABELS,
        ),

        make_fmt_record(
            message_type=5,
            message_length=EV_MESSAGE_LENGTH,
            name="EV",
            fmt=EV_FMT,
            labels=EV_LABELS,
        ),

        make_fmt_record(
            message_type=6,
            message_length=ERR_MESSAGE_LENGTH,
            name="ERR",
            fmt=ERR_FMT,
            labels=ERR_LABELS,
        ),

        make_fmt_record(
            message_type=7,
            message_length=MAVC_MESSAGE_LENGTH,
            name="MAVC",
            fmt=MAVC_FMT,
            labels=MAVC_LABELS,
        ),
    ]


# ============================================================
# GPS RECORD
# ============================================================

def make_gps_record(
    time_us,
    latitude,
    longitude,
    altitude,
    relative_altitude,
    speed,
    ground_course,
    vz,
    satellites,
    hdop,
):
    """
    Create one synthetic GPS DataFlash record.

    Parameters are supplied in human-readable units.

    latitude/longitude:
        degrees

    altitude:
        meters

    relative_altitude:
        meters

    speed:
        m/s

    ground_course:
        degrees

    vz:
        m/s
    """

    latitude_raw = int(
        round(latitude * 1e7)
    )

    longitude_raw = int(
        round(longitude * 1e7)
    )

    altitude_raw = int(
        round(altitude * 100)
    )

    _relative_altitude_raw = int(
        round(relative_altitude * 100)
    )

    payload = struct.pack(
        GPS_PYTHON_FMT,

        # Q: TimeUS
        time_us,

        # B: GPS instance
        0,

        # B: GPS status
        # 3 = 3D fix
        3,

        # I: GPS time in milliseconds
        100000,

        # H: GPS week
        2400,

        # B: number of satellites
        satellites,

        # h: HDop
        hdop,

        # i: latitude * 1e7
        latitude_raw,

        # i: longitude * 1e7
        longitude_raw,

        # i: altitude
        altitude_raw,

        # f: speed
        speed,

        # f: ground course
        ground_course,

        # f: vertical velocity
        vz,

        # f: yaw
        90.0,

        # B: GPS usage flag
        1,
    )

    if len(payload) != GPS_PAYLOAD_SIZE:
        raise ValueError(
            "GPS payload size mismatch: "
            f"{len(payload)} != {GPS_PAYLOAD_SIZE}"
        )

    return make_data_record(
        message_type=1,
        payload=payload,
    )


# ============================================================
# POS RECORD
# ============================================================

def make_pos_record(
    time_us,
    latitude,
    longitude,
    altitude,
    relative_home_altitude,
    relative_origin_altitude,
):
    """
    Create one synthetic ArduPilot POS DataFlash record.

    Parameters are supplied in human-readable units.

    latitude/longitude:
        degrees

    altitude:
        meters

    relative_home_altitude:
        meters

    relative_origin_altitude:
        meters
    """

    latitude_raw = int(
        round(latitude * 1e7)
    )

    longitude_raw = int(
        round(longitude * 1e7)
    )

    payload = struct.pack(
        POS_PYTHON_FMT,

        # Q: TimeUS
        time_us,

        # L: latitude * 1e7
        latitude_raw,

        # L: longitude * 1e7
        longitude_raw,

        # f: canonical altitude
        altitude,

        # f: altitude relative to home
        relative_home_altitude,

        # f: altitude relative to navigation origin
        relative_origin_altitude,
    )

    if len(payload) != POS_PAYLOAD_SIZE:
        raise ValueError(
            "POS payload size mismatch: "
            f"{len(payload)} != {POS_PAYLOAD_SIZE}"
        )

    return make_data_record(
        message_type=8,
        payload=payload,
    )


# ============================================================
# BATTERY RECORD
# ============================================================

def make_bat_record(
    time_us,
    instance,
    voltage,
    voltage_resting,
    current,
    consumed_mah,
    consumed_wh,
    temperature,
    resistance,
    remaining_percent,
    healthy,
    state_of_health,
):
    """
    Create one synthetic BAT DataFlash record.

    Parameters:

        voltage:
            volts

        voltage_resting:
            volts

        current:
            amperes

        consumed_mah:
            mAh

        consumed_wh:
            Wh

        temperature:
            degrees Celsius

        resistance:
            Ohms

        remaining_percent:
            percentage, 0-100

        healthy:
            0 or 1

        state_of_health:
            percentage
    """

    # ArduPilot 'c' is an int16 field.
    # The fixture stores temperature as °C * 100.
    temperature_raw = int(
        round(temperature * 100)
    )

    payload = struct.pack(
        BAT_PYTHON_FMT,

        # Q: TimeUS
        time_us,

        # B: battery instance
        instance,

        # f: battery voltage
        voltage,

        # f: resistance-compensated voltage
        voltage_resting,

        # f: current
        current,

        # f: consumed current / charge
        consumed_mah,

        # f: consumed energy
        consumed_wh,

        # h: temperature * 100
        temperature_raw,

        # f: internal resistance
        resistance,

        # B: remaining percentage
        remaining_percent,

        # B: battery health
        healthy,

        # B: state of health
        state_of_health,
    )

    if len(payload) != BAT_PAYLOAD_SIZE:
        raise ValueError(
            "BAT payload size mismatch: "
            f"{len(payload)} != {BAT_PAYLOAD_SIZE}"
        )

    return make_data_record(
        message_type=9,
        payload=payload,
    )


# ============================================================
# PARM RECORD
# ============================================================

def make_parm_record(
    time_us,
    name,
    value,
    default,
):
    """
    Create a synthetic PARM record.
    """

    payload = struct.pack(
        PARM_PYTHON_FMT,
        time_us,
        fixed_string(name, 16),
        value,
        default,
    )

    if len(payload) != PARM_PAYLOAD_SIZE:
        raise ValueError(
            "PARM payload size mismatch: "
            f"{len(payload)} != {PARM_PAYLOAD_SIZE}"
        )

    return make_data_record(
        message_type=2,
        payload=payload,
    )


# ============================================================
# MODE RECORD
# ============================================================

def make_mode_record(
    time_us,
    mode,
    mode_num,
    reason,
):
    """
    Create a synthetic MODE record.
    """

    payload = struct.pack(
        MODE_PYTHON_FMT,
        time_us,
        mode,
        mode_num,
        reason,
    )

    if len(payload) != MODE_PAYLOAD_SIZE:
        raise ValueError(
            "MODE payload size mismatch: "
            f"{len(payload)} != {MODE_PAYLOAD_SIZE}"
        )

    return make_data_record(
        message_type=3,
        payload=payload,
    )


# ============================================================
# ARM RECORD
# ============================================================

def make_arm_record(
    time_us,
    arm_state,
    arm_checks,
    forced,
    method,
):
    """
    Create a synthetic ARM record.
    """

    payload = struct.pack(
        ARM_PYTHON_FMT,
        time_us,
        arm_state,
        arm_checks,
        forced,
        method,
    )

    if len(payload) != ARM_PAYLOAD_SIZE:
        raise ValueError(
            "ARM payload size mismatch: "
            f"{len(payload)} != {ARM_PAYLOAD_SIZE}"
        )

    return make_data_record(
        message_type=4,
        payload=payload,
    )


# ============================================================
# EV RECORD
# ============================================================

def make_event_record(
    time_us,
    event_id,
):
    """
    Create a synthetic EV record.
    """

    payload = struct.pack(
        EV_PYTHON_FMT,
        time_us,
        event_id,
    )

    if len(payload) != EV_PAYLOAD_SIZE:
        raise ValueError(
            "EV payload size mismatch: "
            f"{len(payload)} != {EV_PAYLOAD_SIZE}"
        )

    return make_data_record(
        message_type=5,
        payload=payload,
    )


# ============================================================
# ERR RECORD
# ============================================================

def make_error_record(
    time_us,
    subsystem,
    error_code,
):
    """
    Create a synthetic ERR record.
    """

    payload = struct.pack(
        ERR_PYTHON_FMT,
        time_us,
        subsystem,
        error_code,
    )

    if len(payload) != ERR_PAYLOAD_SIZE:
        raise ValueError(
            "ERR payload size mismatch: "
            f"{len(payload)} != {ERR_PAYLOAD_SIZE}"
        )

    return make_data_record(
        message_type=6,
        payload=payload,
    )


# ============================================================
# MAVC RECORD
# ============================================================

def make_mavc_record(
    time_us,
    target_system,
    target_component,
    source_system,
    source_component,
    frame,
    command,
    param1,
    param2,
    param3,
    param4,
    x,
    y,
    z,
    result,
    was_command_long,
):
    """
    Create a synthetic MAVC command record.

    Field order:

        TimeUS
        TS
        TC
        SS
        SC
        Fr
        Cmd
        P1
        P2
        P3
        P4
        X
        Y
        Z
        Res
        WL
    """

    payload = struct.pack(
        MAVC_PYTHON_FMT,

        # Q: TimeUS
        time_us,

        # B: target system
        target_system,

        # B: target component
        target_component,

        # B: source system
        source_system,

        # B: source component
        source_component,

        # B: frame
        frame,

        # H: command ID
        command,

        # f: P1
        param1,

        # f: P2
        param2,

        # f: P3
        param3,

        # f: P4
        param4,

        # i: X
        x,

        # i: Y
        y,

        # f: Z
        z,

        # B: result
        result,

        # B: was command long
        was_command_long,
    )

    if len(payload) != MAVC_PAYLOAD_SIZE:
        raise ValueError(
            "MAVC payload size mismatch: "
            f"{len(payload)} != {MAVC_PAYLOAD_SIZE}"
        )

    return make_data_record(
        message_type=7,
        payload=payload,
    )


# ============================================================
# BUILD COMPLETE FIXTURE
# ============================================================

def build_fixture():
    """
    Build the complete synthetic DataFlash file.
    """

    records = []

    # ========================================================
    # FMT RECORDS
    # ========================================================

    records.extend(
        build_fmt_records()
    )

    # ========================================================
    # GPS RECORD #1
    # ========================================================

    records.append(
        make_gps_record(
            time_us=1_000_000,
            latitude=47.3979450,
            longitude=8.5461760,
            altitude=230.0,
            relative_altitude=2.3,
            speed=0.50,
            ground_course=90.0,
            vz=0.0,
            satellites=10,
            hdop=70,
        )
    )

    # ========================================================
    # GPS RECORD #2
    # ========================================================

    records.append(
        make_gps_record(
            time_us=2_000_000,
            latitude=47.3979451,
            longitude=8.5461761,
            altitude=231.0,
            relative_altitude=2.4,
            speed=0.75,
            ground_course=91.0,
            vz=-0.1,
            satellites=11,
            hdop=68,
        )
    )

    # ========================================================
    # POS RECORD #1
    # ========================================================

    records.append(
        make_pos_record(
            time_us=1_500_000,
            latitude=47.39794505,
            longitude=8.54617605,
            altitude=230.5,
            relative_home_altitude=2.35,
            relative_origin_altitude=2.30,
        )
    )

    # ========================================================
    # POS RECORD #2
    # ========================================================

    records.append(
        make_pos_record(
            time_us=2_500_000,
            latitude=47.39794515,
            longitude=8.54617615,
            altitude=231.5,
            relative_home_altitude=2.45,
            relative_origin_altitude=2.40,
        )
    )

    # ========================================================
    # BATTERY RECORD #1
    # ========================================================

    records.append(
        make_bat_record(
            time_us=1_750_000,
            instance=0,
            voltage=16.20,
            voltage_resting=16.25,
            current=2.50,
            consumed_mah=12.50,
            consumed_wh=0.21,
            temperature=25.0,
            resistance=0.015,
            remaining_percent=98,
            healthy=1,
            state_of_health=100,
        )
    )

    # ========================================================
    # BATTERY RECORD #2
    # ========================================================

    records.append(
        make_bat_record(
            time_us=2_750_000,
            instance=0,
            voltage=16.05,
            voltage_resting=16.15,
            current=4.00,
            consumed_mah=18.75,
            consumed_wh=0.31,
            temperature=26.5,
            resistance=0.016,
            remaining_percent=96,
            healthy=1,
            state_of_health=100,
        )
    )

    # ========================================================
    # PARAMETER
    # ========================================================

    records.append(
        make_parm_record(
            time_us=2_500_000,
            name="GPS_TYPE",
            value=1.0,
            default=1.0,
        )
    )

    # ========================================================
    # FLIGHT MODE
    # ========================================================

    records.append(
        make_mode_record(
            time_us=3_000_000,
            mode=4,
            mode_num=4,
            reason=1,
        )
    )

    # ========================================================
    # ARM EVENT
    # ========================================================

    records.append(
        make_arm_record(
            time_us=3_500_000,
            arm_state=1,
            arm_checks=0,
            forced=0,
            method=1,
        )
    )

    # ========================================================
    # EVENT
    # ========================================================

    records.append(
        make_event_record(
            time_us=4_000_000,
            event_id=10,
        )
    )

    # ========================================================
    # ERROR
    # ========================================================

    records.append(
        make_error_record(
            time_us=4_500_000,
            subsystem=2,
            error_code=2,
        )
    )

    # ========================================================
    # MAVC COMMAND
    # ========================================================

    records.append(
        make_mavc_record(
            time_us=5_000_000,

            # Target
            target_system=1,
            target_component=1,

            # Source
            source_system=255,
            source_component=190,

            # MAVLink frame
            frame=0,

            # Command ID
            command=400,

            # Parameters
            param1=0.0,
            param2=0.0,
            param3=0.0,
            param4=0.0,

            # Position
            x=0,
            y=0,
            z=0.0,

            # Result
            result=0,

            # Command-long indicator
            was_command_long=1,
        )
    )

    return b"".join(records)


# ============================================================
# PRINT STRUCTURE INFORMATION
# ============================================================

def print_structure_information():
    """
    Print all generated structure sizes.
    """

    print()

    print(
        f"GPS payload:       {GPS_PAYLOAD_SIZE} bytes"
    )
    print(
        f"GPS record:        {GPS_MESSAGE_LENGTH} bytes"
    )

    print(
        f"POS payload:       {POS_PAYLOAD_SIZE} bytes"
    )
    print(
        f"POS record:        {POS_MESSAGE_LENGTH} bytes"
    )

    print(
        f"BAT payload:       {BAT_PAYLOAD_SIZE} bytes"
    )
    print(
        f"BAT record:        {BAT_MESSAGE_LENGTH} bytes"
    )

    print(
        f"PARM payload:      {PARM_PAYLOAD_SIZE} bytes"
    )
    print(
        f"PARM record:       {PARM_MESSAGE_LENGTH} bytes"
    )

    print(
        f"MODE payload:      {MODE_PAYLOAD_SIZE} bytes"
    )
    print(
        f"MODE record:       {MODE_MESSAGE_LENGTH} bytes"
    )

    print(
        f"ARM payload:       {ARM_PAYLOAD_SIZE} bytes"
    )
    print(
        f"ARM record:        {ARM_MESSAGE_LENGTH} bytes"
    )

    print(
        f"EV payload:        {EV_PAYLOAD_SIZE} bytes"
    )
    print(
        f"EV record:         {EV_MESSAGE_LENGTH} bytes"
    )

    print(
        f"ERR payload:       {ERR_PAYLOAD_SIZE} bytes"
    )
    print(
        f"ERR record:        {ERR_MESSAGE_LENGTH} bytes"
    )

    print(
        f"MAVC payload:      {MAVC_PAYLOAD_SIZE} bytes"
    )
    print(
        f"MAVC record:       {MAVC_MESSAGE_LENGTH} bytes"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    """
    Generate the synthetic ArduPilot forensic fixture.
    """

    validate_structure_sizes()

    output_path = (
        Path(__file__).resolve().parent
        / "synthetic_ardupilot_forensics.bin"
    )

    data = build_fixture()

    output_path.write_bytes(data)

    print("=" * 60)
    print("SYNTHETIC ARDUPILOT FORENSICS FIXTURE")
    print("=" * 60)

    print()
    print("Output:")
    print(output_path)

    print()
    print("Total size:")
    print(f"{len(data)} bytes")

    print_structure_information()

    print()
    print("FMT records:")

    print(
        f"  GPS   -> type 1, length {GPS_MESSAGE_LENGTH}"
    )

    print(
        f"  PARM  -> type 2, length {PARM_MESSAGE_LENGTH}"
    )

    print(
        f"  MODE  -> type 3, length {MODE_MESSAGE_LENGTH}"
    )

    print(
        f"  ARM   -> type 4, length {ARM_MESSAGE_LENGTH}"
    )

    print(
        f"  EV    -> type 5, length {EV_MESSAGE_LENGTH}"
    )

    print(
        f"  ERR   -> type 6, length {ERR_MESSAGE_LENGTH}"
    )

    print(
        f"  MAVC  -> type 7, length {MAVC_MESSAGE_LENGTH}"
    )

    print(
        f"  POS   -> type 8, length {POS_MESSAGE_LENGTH}"
    )

    print(
        f"  BAT   -> type 9, length {BAT_MESSAGE_LENGTH}"
    )

    print()
    print("Data records:")

    print("  GPS   x2")
    print("  POS   x2")
    print("  BAT   x2")
    print("  PARM  x1")
    print("  MODE  x1")
    print("  ARM   x1")
    print("  EV    x1")
    print("  ERR   x1")
    print("  MAVC  x1")

    print()
    print("Expected forensic content:")

    print("  GPS samples:        2")
    print("  Battery samples:    2")
    print("  Commands:           1")
    print("  Command ACKs:       0")
    print("  States:             2")
    print("  Parameters:         1")
    print("  Events:             2")
    print("  Navigation samples: 2")

    print()
    print("Expected MAVC command ID:")
    print("  Cmd = 400")

    print()
    print("Fixture created successfully.")


if __name__ == "__main__":
    main()