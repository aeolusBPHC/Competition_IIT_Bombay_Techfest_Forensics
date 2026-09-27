from pathlib import Path
import struct


OUTPUT = Path("tests/fixtures/synthetic_ardupilot.bin")


HEADER = b"\xA3\x95"


def make_fmt_message(message_id, message_length, name, fmt, labels):
    name_bytes = name.encode("ascii")[:4].ljust(4, b"\x00")
    fmt_bytes = fmt.encode("ascii")[:16].ljust(16, b"\x00")
    labels_bytes = labels.encode("ascii")[:64].ljust(64, b"\x00")

    record = (
        HEADER
        + bytes([128])
        + bytes([message_id])
        + bytes([message_length])
        + name_bytes
        + fmt_bytes
        + labels_bytes
    )

    return record


def make_gps_message(timestamp, latitude, longitude, altitude):
    """
    Synthetic GPS record.

    The exact schema is defined by the FMT record above.
    """

    message_id = 1

    payload = struct.pack(
        "<Iiii",
        timestamp,
        latitude,
        longitude,
        altitude,
    )

    return (
        HEADER
        + bytes([message_id])
        + payload
    )


def main():
    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = bytearray()

    # ---------------------------------------------------------
    # FMT definition for GPS
    # ---------------------------------------------------------

    data.extend(
        make_fmt_message(
            message_id=1,
            message_length=19,
            name="GPS",
            fmt="Iiii",
            labels="TimeUS,Lat,Lon,Alt",
        )
    )

    # ---------------------------------------------------------
    # Synthetic GPS records
    # ---------------------------------------------------------

    data.extend(
        make_gps_message(
            timestamp=1000000,
            latitude=473979450,
            longitude=85461760,
            altitude=230,
        )
    )

    data.extend(
        make_gps_message(
            timestamp=2000000,
            latitude=473979451,
            longitude=85461761,
            altitude=231,
        )
    )

    data.extend(
        make_gps_message(
            timestamp=3000000,
            latitude=473979452,
            longitude=85461762,
            altitude=232,
        )
    )

    OUTPUT.write_bytes(data)

    print("Synthetic DataFlash fixture created:")
    print(OUTPUT)
    print("Size:", len(data), "bytes")


if __name__ == "__main__":
    main()
