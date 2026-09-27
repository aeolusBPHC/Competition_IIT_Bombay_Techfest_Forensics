from pathlib import Path


OUTPUT = (
    Path(__file__).resolve().parent
    / "synthetic_betaflight_blackbox.bbl"
)


def encode_unsigned_vb(value: int) -> bytes:
    """
    Encode an unsigned integer using Blackbox variable-byte encoding.
    """

    if value < 0:
        raise ValueError(
            "Unsigned variable-byte value cannot be negative"
        )

    output = bytearray()

    while True:
        byte = value & 0x7F
        value >>= 7

        if value:
            byte |= 0x80

        output.append(byte)

        if not value:
            break

    return bytes(output)


def encode_signed_vb(value: int) -> bytes:
    """
    Encode a signed integer using Blackbox signed variable-byte encoding.
    """

    if value < 0:
        encoded = ((-value) << 1) | 1
    else:
        encoded = value << 1

    return encode_unsigned_vb(encoded)


def encode_neg_14bit(value: int) -> bytes:
    """
    NEG_14BIT is stored as a 14-bit unsigned value.

    The fixture uses values that fit directly into the 14-bit range.
    """

    if value < 0 or value > 0x3FFF:
        raise ValueError(
            "NEG_14BIT value must fit in 14 bits"
        )

    return encode_unsigned_vb(
        value & 0x3FFF
    )


def build_header() -> bytes:
    lines = [
        "H Product:Blackbox flight data recorder by Nicholas Sherlock",
        "H Data version:2",
        "H Firmware type:Betaflight",
        "H Firmware revision:4.5.0",
        "H Firmware date:2026-09-24",
        "H Firmware time:12:00:00",

        # --------------------------------------------------------------
        # Battery calibration
        # --------------------------------------------------------------

        "H vbatref:1838",
        "H vbatscale:110",
        "H vbat_divider:10",
        "H vbat_multiplier:1",

        # currentMeter = offset, scale
        #
        # With scale 806, the synthetic amperage ADC values below
        # correspond approximately to 2.50 A and 4.00 A.
        #
        "H currentMeter:0,806",

        # --------------------------------------------------------------
        # Home frame
        # --------------------------------------------------------------

        "H Field H name = time,GPS_home[0],GPS_home[1]",
        "H Field H signed = U,S,S",
        "H Field H predictor = 0,0,0",
        "H Field H encoding = UNSIGNED_VB,SIGNED_VB,SIGNED_VB",

        # --------------------------------------------------------------
        # GPS frame
        # --------------------------------------------------------------

        "H Field G name = time,GPS_numSat,GPS_coord[0],GPS_coord[1],GPS_altitude,GPS_speed,GPS_ground_course",
        "H Field G signed = U,U,S,S,S,U,U",
        "H Field G predictor = 0,0,HOME_COORD,HOME_COORD,0,0,0",
        "H Field G encoding = UNSIGNED_VB,UNSIGNED_VB,SIGNED_VB,SIGNED_VB,SIGNED_VB,UNSIGNED_VB,UNSIGNED_VB",

        # --------------------------------------------------------------
        # Main/intra frame
        # --------------------------------------------------------------

        "H Field I name = time,vbatLatest,amperageLatest",
        "H Field I signed = U,U,S",
        "H Field I predictor = 0,9,0",
        "H Field I encoding = UNSIGNED_VB,NEG_14BIT,SIGNED_VB",
    ]

    return (
        "\n".join(lines)
        + "\n"
    ).encode("ascii")


def build_fixture() -> bytes:
    data = bytearray()

    data.extend(
        build_header()
    )

    # ==============================================================
    # H frame
    # ==============================================================

    data.append(ord("H"))

    # time = 0
    data.extend(
        encode_unsigned_vb(0)
    )

    # GPS home latitude:
    # 47.397945 -> 473979450
    data.extend(
        encode_signed_vb(
            473_979_450
        )
    )

    # GPS home longitude:
    # 8.546176 -> 85461760
    data.extend(
        encode_signed_vb(
            85_461_760
        )
    )

    # ==============================================================
    # G frame 1
    # ==============================================================

    data.append(ord("G"))

    # time = 1,000,000 us
    data.extend(
        encode_unsigned_vb(
            1_000_000
        )
    )

    # GPS_numSat = 10
    data.extend(
        encode_unsigned_vb(10)
    )

    # GPS latitude = HOME_COORD
    data.extend(
        encode_signed_vb(0)
    )

    # GPS longitude = HOME_COORD
    data.extend(
        encode_signed_vb(0)
    )

    # GPS altitude = 2300 decimeters = 230 m
    data.extend(
        encode_signed_vb(2300)
    )

    # GPS speed = 500 -> 5.00 m/s
    data.extend(
        encode_unsigned_vb(500)
    )

    # GPS ground course = 900 -> 90 degrees
    data.extend(
        encode_unsigned_vb(900)
    )

    # ==============================================================
    # G frame 2
    # ==============================================================

    data.append(ord("G"))

    # time = 2,000,000 us
    data.extend(
        encode_unsigned_vb(
            2_000_000
        )
    )

    # GPS_numSat = 11
    data.extend(
        encode_unsigned_vb(11)
    )

    # Latitude delta = +10
    data.extend(
        encode_signed_vb(10)
    )

    # Longitude delta = +20
    data.extend(
        encode_signed_vb(20)
    )

    # GPS altitude = 2310 decimeters = 231 m
    data.extend(
        encode_signed_vb(2310)
    )

    # GPS speed = 750 -> 7.50 m/s
    data.extend(
        encode_unsigned_vb(750)
    )

    # GPS ground course = 920 -> 92 degrees
    data.extend(
        encode_unsigned_vb(920)
    )

    # ==============================================================
    # I frame 1
    # ==============================================================

    data.append(ord("I"))

    # time = 3,000,000 us
    data.extend(
        encode_unsigned_vb(
            3_000_000
        )
    )

    # vbatLatest is predicted from VBATREF.
    #
    # vbatref = 1838
    # desired raw vbat = 1818
    # stored difference = 1838 - 1818 = 20
    #
    data.extend(
        encode_neg_14bit(20)
    )

    # amperageLatest raw ADC value.
    #
    # With currentMeter:0,806 this gives approximately 2.50 A.
    data.extend(
        encode_signed_vb(250)
    )

    # ==============================================================
    # I frame 2
    # ==============================================================

    data.append(ord("I"))

    # time = 4,000,000 us
    data.extend(
        encode_unsigned_vb(
            4_000_000
        )
    )

    # vbatref = 1838
    # desired raw vbat = 1795
    # stored difference = 1838 - 1795 = 43
    data.extend(
        encode_neg_14bit(43)
    )

    # amperageLatest -> approximately 4.00 A
    data.extend(
        encode_signed_vb(400)
    )

    return bytes(data)


def main():
    fixture = build_fixture()

    OUTPUT.write_bytes(
        fixture
    )

    print(
        f"Created Betaflight fixture: {OUTPUT}"
    )

    print(
        f"Size: {len(fixture)} bytes"
    )


if __name__ == "__main__":
    main()