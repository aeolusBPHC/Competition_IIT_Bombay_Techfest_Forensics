from pathlib import Path


OUTPUT = (
    Path(__file__).parent
    / "synthetic_inav_blackbox.bbl"
)


def encode_unsigned_vb(value: int) -> bytes:

    if value < 0:
        raise ValueError(
            "UNSIGNED_VB cannot encode negative values"
        )

    result = bytearray()

    while True:

        byte = value & 0x7F
        value >>= 7

        if value:
            byte |= 0x80

        result.append(byte)

        if not value:
            break

    return bytes(result)


def encode_signed_vb(value: int) -> bytes:

    if value >= 0:
        encoded = value << 1
    else:
        encoded = ((-value) << 1) - 1

    return encode_unsigned_vb(encoded)


def encode_field(
    value: int,
    encoding: str,
) -> bytes:

    if encoding == "0":
        return encode_signed_vb(value)

    if encoding == "1":
        return encode_unsigned_vb(value)

    raise ValueError(
        f"Unsupported encoding: {encoding}"
    )


def main():

    header = b"""\
H Product:Blackbox flight data recorder by Nicholas Sherlock
H Data version:2
H Firmware type:INAV
H Firmware revision:7.1.0
H Firmware date:2026-09-24
H Firmware time:12:00:00
H Field H name:GPS_home[0],GPS_home[1],GPS_home[2],GPS_home_epoch
H Field H signed:1,1,1,0
H Field H predictor:0,0,0,0
H Field H encoding:0,0,0,1
H Field G name:time,GPS_fixType,GPS_numSat,GPS_coord[0],GPS_coord[1],GPS_altitude,GPS_speed,GPS_ground_course,GPS_velned[0],GPS_velned[1],GPS_velned[2],GPS_time
H Field G signed:0,0,0,1,1,1,0,0,1,1,1,0
H Field G predictor:10,0,0,7,7,0,0,0,0,0,0,0
H Field G encoding:1,1,1,0,0,0,1,1,0,0,0,1
"""

    frames = bytearray()

    home_lat = 473979450
    home_lon = 85461760

    # ---------------------------------------------------------------
    # H frame
    # ---------------------------------------------------------------

    frames.append(ord("H"))

    frames.extend(
        encode_field(
            home_lat,
            "0",
        )
    )

    frames.extend(
        encode_field(
            home_lon,
            "0",
        )
    )

    frames.extend(
        encode_field(
            2300,
            "0",
        )
    )

    frames.extend(
        encode_field(
            1_000_000,
            "1",
        )
    )

    # ---------------------------------------------------------------
    # G frame 1
    # ---------------------------------------------------------------

    frames.append(ord("G"))

    # time
    frames.extend(
        encode_field(
            1_000_000,
            "1",
        )
    )

    # GPS fix type
    frames.extend(
        encode_field(
            3,
            "1",
        )
    )

    # satellites
    frames.extend(
        encode_field(
            10,
            "1",
        )
    )

    # latitude delta from home
    frames.extend(
        encode_field(
            0,
            "0",
        )
    )

    # longitude delta from home
    frames.extend(
        encode_field(
            0,
            "0",
        )
    )

    # altitude = 230 m
    frames.extend(
        encode_field(
            230,
            "0",
        )
    )

    # speed = 5 m/s => 500 cm/s
    frames.extend(
        encode_field(
            500,
            "1",
        )
    )

    # ground course = 90 degrees => 900
    frames.extend(
        encode_field(
            900,
            "1",
        )
    )

    # velocity N/E/D, cm/s
    frames.extend(
        encode_field(
            300,
            "0",
        )
    )

    frames.extend(
        encode_field(
            400,
            "0",
        )
    )

    frames.extend(
        encode_field(
            0,
            "0",
        )
    )

    # GPS time
    frames.extend(
        encode_field(
            12_000,
            "1",
        )
    )

    # ---------------------------------------------------------------
    # G frame 2
    # ---------------------------------------------------------------

    frames.append(ord("G"))

    frames.extend(
        encode_field(
            2_000_000,
            "1",
        )
    )

    frames.extend(
        encode_field(
            3,
            "1",
        )
    )

    frames.extend(
        encode_field(
            12,
            "1",
        )
    )

    frames.extend(
        encode_field(
            10,
            "0",
        )
    )

    frames.extend(
        encode_field(
            20,
            "0",
        )
    )

    frames.extend(
        encode_field(
            231,
            "0",
        )
    )

    frames.extend(
        encode_field(
            750,
            "1",
        )
    )

    frames.extend(
        encode_field(
            920,
            "1",
        )
    )

    frames.extend(
        encode_field(
            500,
            "0",
        )
    )

    frames.extend(
        encode_field(
            600,
            "0",
        )
    )

    frames.extend(
        encode_field(
            -50,
            "0",
        )
    )

    frames.extend(
        encode_field(
            12_001,
            "1",
        )
    )

    OUTPUT.write_bytes(
        header + bytes(frames)
    )

    print(
        f"Created: {OUTPUT}"
    )

    print(
        f"Size: {OUTPUT.stat().st_size} bytes"
    )


if __name__ == "__main__":
    main()
