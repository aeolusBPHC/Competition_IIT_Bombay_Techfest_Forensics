from pathlib import Path
import struct

from pymavlink import mavutil


OUTPUT = Path(
    "tests/fixtures/synthetic_mavlink_gps.tlog"
)


def make_message(
    time_usec,
    latitude,
    longitude,
    altitude_m,
    speed_m_s,
    fix_type,
    satellites,
    hdop,
    vdop,
    heading_deg,
):
    return mavutil.mavlink.MAVLink_gps_raw_int_message(
        time_usec=time_usec,
        fix_type=fix_type,
        lat=int(latitude * 1e7),
        lon=int(longitude * 1e7),
        alt=int(altitude_m * 1000),
        eph=int(hdop * 100),
        epv=int(vdop * 100),
        vel=int(speed_m_s * 100),
        cog=int(heading_deg * 100),
        satellites_visible=satellites,
    )

def make_global_position_message(
    time_boot_ms,
    latitude,
    longitude,
    altitude_m,
    relative_altitude_m,
    vx_m_s,
    vy_m_s,
    vz_m_s,
    heading_deg,
):
    return mavutil.mavlink.MAVLink_global_position_int_message(
        time_boot_ms=time_boot_ms,
        lat=int(latitude * 1e7),
        lon=int(longitude * 1e7),
        alt=int(altitude_m * 1000),
        relative_alt=int(relative_altitude_m * 1000),
        vx=int(vx_m_s * 100),
        vy=int(vy_m_s * 100),
        vz=int(vz_m_s * 100),
        hdg=int(heading_deg * 100),
    )

def make_battery_status_message(
    battery_id,
    temperature_c,
    cell_voltages_v,
    current_a,
    discharged_mah,
    battery_remaining,
):
    voltages = [
        int(round(voltage * 1000))
        for voltage in cell_voltages_v
    ]

    while len(voltages) < 10:
        voltages.append(65535)

    return mavutil.mavlink.MAVLink_battery_status_message(
        id=battery_id,
        battery_function=0,
        type=0,
        temperature=int(temperature_c * 100),
        voltages=voltages,
        current_battery=int(current_a * 100),
        current_consumed=int(discharged_mah),
        energy_consumed=210,
        battery_remaining=int(battery_remaining),
    )

def main():
    mav = mavutil.mavlink.MAVLink(None)

    mav.srcSystem = 1
    mav.srcComponent = 1

    messages = [
        make_message(
            time_usec=1_000_000,
            latitude=47.3979450,
            longitude=8.5461760,
            altitude_m=230.0,
            speed_m_s=0.50,
            fix_type=3,
            satellites=10,
            hdop=0.70,
            vdop=0.80,
            heading_deg=90.0,
        ),
        make_message(
            time_usec=2_000_000,
            latitude=47.3979451,
            longitude=8.5461761,
            altitude_m=231.0,
            speed_m_s=0.75,
            fix_type=3,
            satellites=11,
            hdop=0.65,
            vdop=0.75,
            heading_deg=92.0,
        ),
        make_global_position_message(
        time_boot_ms=3_000,
        latitude=47.3979460,
        longitude=8.5461770,
        altitude_m=232.0,
        relative_altitude_m=12.0,
        vx_m_s=1.00,
        vy_m_s=2.00,
        vz_m_s=-0.50,
        heading_deg=95.0,
        ),
        make_global_position_message(
        time_boot_ms=4_000,
        latitude=47.3979461,
        longitude=8.5461771,
        altitude_m=233.0,
        relative_altitude_m=13.0,
        vx_m_s=1.50,
        vy_m_s=2.50,
        vz_m_s=-0.25,
        heading_deg=97.0,
        ),
        make_battery_status_message(
            battery_id=1,
            temperature_c=25.0,
            cell_voltages_v=[
                4.05,
                4.05,
                4.05,
                4.05,
            ],
            current_a=2.50,
            discharged_mah=12500,
            battery_remaining=98,
        ),

        make_battery_status_message(
            battery_id=1,
            temperature_c=26.5,
            cell_voltages_v=[
                4.01,
                4.02,
                4.01,
                4.01,
            ],
            current_a=4.00,
            discharged_mah=12518,
            battery_remaining=96,
        ),
    ]    

    tlog_records = []

    outer_timestamps = [
        1_700_000_000_000_000,
        1_700_000_001_000_000,
        1_700_000_002_000_000,
        1_700_000_003_000_000,
        1_700_000_004_000_000,
        1_700_000_005_000_000,
    ]

    for timestamp, message in zip(
        outer_timestamps,
        messages,
    ):
        packet = message.pack(mav)

        record = (
            struct.pack(">Q", timestamp)
            + packet
        )

        tlog_records.append(record)

    OUTPUT.write_bytes(
        b"".join(tlog_records)
    )

    print(f"Created: {OUTPUT}")
    print(f"Size: {OUTPUT.stat().st_size} bytes")
    print(f"Records: {len(messages)}")


if __name__ == "__main__":
    main()
