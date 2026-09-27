from pathlib import Path
import struct

from pymavlink import mavutil


OUTPUT = Path(__file__).parent / "synthetic_ardupilot.tlog"


def build_message(mav, message):
    return message.pack(mav)


def timestamped_packet(timestamp_us, packet):
    return struct.pack(">Q", timestamp_us) + packet


def main():
    # Create a MAVLink 1 encoder.
    mav = mavutil.mavlink.MAVLink(None)
    mav.srcSystem = 1
    mav.srcComponent = 1

    packets = []

    # ---------------------------------------------------------
    # 1. ArduPilot-identifying HEARTBEAT
    #
    # autopilot = 3 -> MAV_AUTOPILOT_ARDUPILOTMEGA
    # type = 2      -> MAV_TYPE_QUADROTOR
    # ---------------------------------------------------------
    heartbeat = mavutil.mavlink.MAVLink_heartbeat_message(
        type=2,
        autopilot=3,
        base_mode=0,
        custom_mode=0,
        system_status=4,
        mavlink_version=3,
    )

    packets.append(
        timestamped_packet(
            1_000_000,
            build_message(mav, heartbeat),
        )
    )

    # ---------------------------------------------------------
    # 2. GPS_RAW_INT
    # ---------------------------------------------------------
    gps1 = mavutil.mavlink.MAVLink_gps_raw_int_message(
        time_usec=1_000_000,
        fix_type=3,
        lat=473979453,
        lon=85461763,
        alt=500000,
        eph=100,
        epv=100,
        vel=100,
        cog=9000,
        satellites_visible=10,
    )

    packets.append(
        timestamped_packet(
            2_000_000,
            build_message(mav, gps1),
        )
    )

    # ---------------------------------------------------------
    # 3. Another GPS_RAW_INT
    # ---------------------------------------------------------
    gps2 = mavutil.mavlink.MAVLink_gps_raw_int_message(
        time_usec=2_000_000,
        fix_type=3,
        lat=473979500,
        lon=85461800,
        alt=510000,
        eph=90,
        epv=90,
        vel=120,
        cog=9500,
        satellites_visible=11,
    )

    packets.append(
        timestamped_packet(
            3_000_000,
            build_message(mav, gps2),
        )
    )

    # ---------------------------------------------------------
    # 4. BATTERY_STATUS
    # ---------------------------------------------------------
    battery1 = mavutil.mavlink.MAVLink_battery_status_message(
        id=0,
        battery_function=0,
        type=0,
        temperature=2500,
        voltages=[12000] + [65535] * 9,
        current_battery=1500,
        current_consumed=100,
        energy_consumed=200,
        battery_remaining=90,
       
    )

    packets.append(
        timestamped_packet(
            4_000_000,
            build_message(mav, battery1),
        )
    )

    # ---------------------------------------------------------
    # Write TLOG
    # ---------------------------------------------------------
    OUTPUT.write_bytes(b"".join(packets))

    print(f"Created: {OUTPUT}")
    print(f"Packets: {len(packets)}")
    print(f"Size: {OUTPUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
