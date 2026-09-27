from pathlib import Path
import struct

from platform_parsers.common.base_parser import BaseForensicParser
from platform_parsers.common.evidence_model import (
    EvidenceMetadata,
    GPSRecord,
    NavigationRecord,
    BatteryRecord,
    NormalizedEvidence,
)

from platform_parsers.mavlink.normalized_extractors import (
    extract_telemetry as extract_mavlink_telemetry,
    extract_failsafe as extract_mavlink_failsafe,
    extract_commands as extract_mavlink_commands,
    extract_command_acks as extract_mavlink_command_acks,
    extract_states as extract_mavlink_states,
    extract_parameters as extract_mavlink_parameters,
    extract_events as extract_mavlink_events,
)


class ArduPilotTLogParser(BaseForensicParser):
    """
    Parser for ArduPilot telemetry logs stored in MAVLink TLOG format.

    Platform identification is conservative:

    - A valid MAVLink TLOG structure alone does NOT identify ArduPilot.
    - ArduPilot identification requires platform-specific MAVLink
      evidence.
    - Currently, HEARTBEAT.autopilot == 3
      (MAV_AUTOPILOT_ARDUPILOTMEGA) is used as the primary
      ArduPilot platform indicator.

    Current extraction scope:
    - TLOG structural detection
    - MAVLink version detection
    - ArduPilot platform identification
    - MAVLink message extraction
    - GPS extraction
    - Navigation extraction
    - Battery extraction
    - Normalized evidence generation

    Supported GPS messages:
    - GPS_RAW_INT
    - GLOBAL_POSITION_INT

    Supported navigation messages:
    - GLOBAL_POSITION_INT

    Supported battery messages:
    - BATTERY_STATUS
    """

    platform_name = "ArduPilot"

    supported_formats = [
        "TLOG",
        ".tlog",
    ]

    TIMESTAMP_SIZE = 8

    # MAVLink enum:
    # MAV_AUTOPILOT_ARDUPILOTMEGA = 3
    ARDUPILOT_AUTOPILOT_ID = 3

    @classmethod
    def identify(cls, evidence_path):
        """
        Identify an ArduPilot TLOG.

        A valid MAVLink TLOG structure is not sufficient to claim
        ArduPilot. Platform-specific evidence must be present.

        Important distinction:

        - supported=True:
            This parser claims the evidence as ArduPilot TLOG.

        - supported=False + format="TLOG":
            The file is structurally recognized as a TLOG, but
            there is insufficient evidence to attribute it to
            ArduPilot.

        - supported=False + format=None:
            The file could not be identified as a valid TLOG.
        """

        path = Path(evidence_path)

        if not path.exists():
            return {
                "supported": False,
                "platform": cls.platform_name,
                "format": None,
                "confidence": "NONE",
                "reason": "File does not exist",
            }

        if not path.is_file():
            return {
                "supported": False,
                "platform": cls.platform_name,
                "format": None,
                "confidence": "NONE",
                "reason": "Evidence path is not a file",
            }

        try:
            result = cls._inspect_tlog(path)

            # --------------------------------------------------
            # Invalid TLOG
            # --------------------------------------------------

            if not result["valid"]:
                return {
                    "supported": False,
                    "platform": cls.platform_name,
                    "format": None,
                    "confidence": "NONE",
                    "reason": result["reason"],
                    "indicators": result.get(
                        "indicators",
                        {},
                    ),
                    "platform_evidence": result.get(
                        "platform_evidence",
                        {},
                    ),
                }

            platform_evidence = result.get(
                "platform_evidence",
                {},
            )

            # --------------------------------------------------
            # Platform-specific ArduPilot evidence
            # --------------------------------------------------

            if platform_evidence.get("ardupilot"):
                return {
                    "supported": True,
                    "platform": cls.platform_name,
                    "format": "TLOG",
                    "confidence": "HIGH",
                    "reason": (
                        "MAVLink TLOG contains platform-specific "
                        "evidence identifying ArduPilot"
                    ),
                    "indicators": result["indicators"],
                    "platform_evidence": platform_evidence,
                }

            # --------------------------------------------------
            # Valid TLOG, but platform is not ArduPilot
            #
            # The format is still known to be TLOG. We therefore
            # preserve format="TLOG" for diagnostic purposes while
            # refusing to claim the platform.
            # --------------------------------------------------

            return {
                "supported": False,
                "platform": cls.platform_name,
                "format": "TLOG",
                "confidence": "NONE",
                "reason": (
                    "Valid MAVLink TLOG detected, but "
                    "ArduPilot-specific platform evidence "
                    "was not found"
                ),
                "indicators": result["indicators"],
                "platform_evidence": platform_evidence,
            }

        except Exception as exc:
            return {
                "supported": False,
                "platform": cls.platform_name,
                "format": None,
                "confidence": "ERROR",
                "reason": f"TLOG validation failed: {exc}",
            }

    @classmethod
    def _inspect_tlog(cls, path):
        """
        Inspect the first portion of a TLOG.

        Each TLOG record is expected to contain:

            8-byte big-endian timestamp
            MAVLink packet

        This method is used for detection only.

        It records:

        - number of valid MAVLink records
        - MAVLink versions
        - message types
        - HEARTBEAT detection
        - HEARTBEAT autopilot values
        - ArduPilot-specific platform evidence

        It does not parse the complete evidence file.
        """

        max_scan = 1024 * 1024

        with path.open("rb") as file:
            data = file.read(max_scan)

        if len(data) < cls.TIMESTAMP_SIZE + 8:
            return {
                "valid": False,
                "reason": (
                    "File is too small to contain a TLOG record"
                ),
                "indicators": {},
                "platform_evidence": {},
            }

        try:
            from pymavlink import mavutil

        except ImportError:
            return {
                "valid": False,
                "reason": "pymavlink is not installed",
                "indicators": {},
                "platform_evidence": {},
            }

        offset = 0
        records = 0

        mavlink_versions = set()
        message_types = []

        # ------------------------------------------------------
        # Platform-specific evidence
        # ------------------------------------------------------

        platform_evidence = {
            "ardupilot": False,
            "heartbeat_detected": False,
            "autopilot_values": [],
            "custom_mode_values": [],
        }

        while (
            offset + cls.TIMESTAMP_SIZE
            < len(data)
        ):
            timestamp_bytes = data[
                offset:
                offset + cls.TIMESTAMP_SIZE
            ]

            timestamp_us = struct.unpack(
                ">Q",
                timestamp_bytes,
            )[0]

            if timestamp_us == 0:
                offset += 1
                continue

            packet_start = (
                offset + cls.TIMESTAMP_SIZE
            )

            magic_index = None

            for candidate in range(
                packet_start,
                min(
                    packet_start + 16,
                    len(data),
                ),
            ):
                if data[candidate] in (
                    0xFE,
                    0xFD,
                ):
                    magic_index = candidate
                    break

            if magic_index is None:
                offset += 1
                continue

            try:
                parser = mavutil.mavlink.MAVLink(
                    None
                )

                message = parser.parse_char(
                    data[magic_index:]
                )

                if message is None:
                    offset += 1
                    continue

                records += 1

                # --------------------------------------------------
                # MAVLink version
                # --------------------------------------------------

                if data[magic_index] == 0xFE:
                    mavlink_versions.add(
                        "MAVLink 1"
                    )

                elif data[magic_index] == 0xFD:
                    mavlink_versions.add(
                        "MAVLink 2"
                    )

                message_type = message.get_type()

                message_types.append(
                    message_type
                )

                # --------------------------------------------------
                # HEARTBEAT / platform identification
                # --------------------------------------------------

                if message_type == "HEARTBEAT":

                    platform_evidence[
                        "heartbeat_detected"
                    ] = True

                    # ----------------------------------------------
                    # Autopilot enum
                    # ----------------------------------------------

                    try:
                        autopilot = int(
                            message.autopilot
                        )

                        platform_evidence[
                            "autopilot_values"
                        ].append(
                            autopilot
                        )

                        if (
                            autopilot
                            == cls.ARDUPILOT_AUTOPILOT_ID
                        ):
                            platform_evidence[
                                "ardupilot"
                            ] = True

                    except (
                        AttributeError,
                        TypeError,
                        ValueError,
                    ):
                        pass

                    # ----------------------------------------------
                    # Custom mode
                    # ----------------------------------------------

                    try:
                        platform_evidence[
                            "custom_mode_values"
                        ].append(
                            int(message.custom_mode)
                        )

                    except (
                        AttributeError,
                        TypeError,
                        ValueError,
                    ):
                        pass

                # Move forward. The existing TLOG detection
                # mechanism advances past the detected packet.
                offset = magic_index + 2

            except Exception:
                offset += 1

        # ------------------------------------------------------
        # No valid MAVLink records
        # ------------------------------------------------------

        if records == 0:
            return {
                "valid": False,
                "reason": (
                    "No valid MAVLink records detected"
                ),
                "indicators": {},
                "platform_evidence": {},
            }

        # ------------------------------------------------------
        # Valid MAVLink TLOG
        # ------------------------------------------------------

        return {
            "valid": True,
            "reason": (
                "MAVLink telemetry records detected "
                "in TLOG-compatible binary structure"
            ),
            "indicators": {
                "records_detected": records,
                "mavlink_versions": sorted(
                    mavlink_versions
                ),
                "message_types": message_types,
            },
            "platform_evidence": platform_evidence,
        }

    def _iter_tlog(self):
        """
        Iterate through the complete TLOG.

        Each record consists of:

            8-byte big-endian timestamp
            MAVLink packet

        The current PoC loads the complete evidence file
        into memory.
        """

        try:
            from pymavlink import mavutil

        except ImportError as exc:
            raise RuntimeError(
                "pymavlink is not installed"
            ) from exc

        data = self.evidence_path.read_bytes()

        offset = 0

        while (
            offset + self.TIMESTAMP_SIZE
            <= len(data)
        ):
            timestamp_offset = offset

            timestamp_us = struct.unpack(
                ">Q",
                data[
                    offset:
                    offset + self.TIMESTAMP_SIZE
                ],
            )[0]

            offset += self.TIMESTAMP_SIZE

            if offset >= len(data):
                break

            magic = data[offset]

            if magic not in (
                0xFE,
                0xFD,
            ):
                raise ValueError(
                    "Invalid MAVLink magic byte at "
                    f"offset {offset}: "
                    f"0x{magic:02x}"
                )

            if offset + 2 > len(data):
                raise ValueError(
                    "Incomplete MAVLink header"
                )

            payload_length = data[
                offset + 1
            ]

            # --------------------------------------------------
            # MAVLink 1
            # --------------------------------------------------

            if magic == 0xFE:

                header_length = 6
                checksum_length = 2
                mavlink_version = "MAVLink 1"

            # --------------------------------------------------
            # MAVLink 2
            # --------------------------------------------------

            else:

                header_length = 10
                checksum_length = 2
                mavlink_version = "MAVLink 2"

                incompat_flags = data[
                    offset + 2
                ]

                # MAVLink 2 signing adds 13 bytes.
                if incompat_flags & 0x01:
                    checksum_length += 13

            packet_length = (
                header_length
                + payload_length
                + checksum_length
            )

            packet_end = (
                offset + packet_length
            )

            if packet_end > len(data):
                raise ValueError(
                    "Incomplete MAVLink packet at "
                    f"offset {offset}"
                )

            packet = data[
                offset:
                packet_end
            ]

            parser = mavutil.mavlink.MAVLink(
                None
            )

            message = parser.parse_char(
                packet
            )

            if message is None:
                raise ValueError(
                    "MAVLink packet could not be decoded "
                    f"at offset {offset}"
                )

            yield {
                "timestamp_us": timestamp_us,
                "timestamp": (
                    timestamp_us / 1_000_000.0
                ),
                "message": message,
                "packet": packet,
                "mavlink_version": mavlink_version,
                "timestamp_offset": timestamp_offset,
                "packet_offset": offset,
            }

            offset = packet_end

    def get_metadata(self):
        """
        Return normalized evidence metadata.
        """

        return EvidenceMetadata(
            source_file=str(
                self.evidence_path
            ),
            platform=self.platform_name,
            format="TLOG",
        )

    def extract_gps(self):
        """
        Extract GPS-related MAVLink messages into normalized
        GPSRecord objects.

        Supported messages:

        GPS_RAW_INT:
            - latitude/longitude: degrees * 1e7
            - altitude: millimeters
            - velocity: centimeters/second
            - heading: centidegrees
            - HDOP/VDOP: value * 0.01

        GLOBAL_POSITION_INT:
            - latitude/longitude: degrees * 1e7
            - altitude: millimeters
            - VX/VY: centimeters/second
            - heading: centidegrees
        """

        gps_records = []

        for record in self._iter_tlog():

            message = record["message"]
            message_type = message.get_type()
            timestamp = record["timestamp"]

            # ==================================================
            # GPS_RAW_INT
            # ==================================================

            if message_type == "GPS_RAW_INT":

                raw = message.to_dict()

                latitude = (
                    message.lat / 1e7
                    if message.lat is not None
                    else None
                )

                longitude = (
                    message.lon / 1e7
                    if message.lon is not None
                    else None
                )

                altitude_m = (
                    message.alt / 1000.0
                    if message.alt is not None
                    else None
                )

                speed_m_s = (
                    message.vel / 100.0
                    if message.vel is not None
                    else None
                )

                hdop = (
                    message.eph / 100.0
                    if message.eph is not None
                    else None
                )

                vdop = (
                    message.epv / 100.0
                    if message.epv is not None
                    else None
                )

                heading_deg = None

                if message.cog is not None:
                    heading_deg = (
                        message.cog / 100.0
                    )

                gps_records.append(
                    GPSRecord(
                        timestamp=timestamp,
                        latitude=latitude,
                        longitude=longitude,
                        altitude_m=altitude_m,
                        speed_m_s=speed_m_s,
                        fix_type=message.fix_type,
                        satellites=(
                            message.satellites_visible
                        ),
                        hdop=hdop,
                        vdop=vdop,
                        heading_deg=heading_deg,
                        source_platform=(
                            self.platform_name
                        ),
                        raw=raw,
                    )
                )

            # ==================================================
            # GLOBAL_POSITION_INT
            # ==================================================

            elif (
                message_type
                == "GLOBAL_POSITION_INT"
            ):

                raw = message.to_dict()

                latitude = (
                    message.lat / 1e7
                    if message.lat is not None
                    else None
                )

                longitude = (
                    message.lon / 1e7
                    if message.lon is not None
                    else None
                )

                altitude_m = (
                    message.alt / 1000.0
                    if message.alt is not None
                    else None
                )

                vx_m_s = (
                    message.vx / 100.0
                    if message.vx is not None
                    else None
                )

                vy_m_s = (
                    message.vy / 100.0
                    if message.vy is not None
                    else None
                )

                speed_m_s = None

                if (
                    vx_m_s is not None
                    and vy_m_s is not None
                ):
                    speed_m_s = (
                        vx_m_s ** 2
                        + vy_m_s ** 2
                    ) ** 0.5

                heading_deg = None

                if (
                    message.hdg is not None
                    and message.hdg != 65535
                ):
                    heading_deg = (
                        message.hdg / 100.0
                    )

                gps_records.append(
                    GPSRecord(
                        timestamp=timestamp,
                        latitude=latitude,
                        longitude=longitude,
                        altitude_m=altitude_m,
                        speed_m_s=speed_m_s,
                        heading_deg=heading_deg,
                        source_platform=(
                            self.platform_name
                        ),
                        raw=raw,
                    )
                )

        return gps_records

    def extract_navigation(self):
        """
        Extract normalized navigation records from
        GLOBAL_POSITION_INT MAVLink messages.

        GLOBAL_POSITION_INT provides:
        - latitude
        - longitude
        - altitude above MSL
        - altitude above home
        - ground velocity
        - vehicle heading

        The outer TLOG timestamp is used as the
        forensic timestamp.
        """

        navigation_records = []

        for record in self._iter_tlog():

            message = record["message"]

            if message.get_type() != "GLOBAL_POSITION_INT":
                continue

            navigation_records.append(
                NavigationRecord(
                    timestamp=record["timestamp"],

                    latitude=(
                        message.lat / 1e7
                        if message.lat is not None
                        else None
                    ),

                    longitude=(
                        message.lon / 1e7
                        if message.lon is not None
                        else None
                    ),

                    altitude_m=(
                        message.alt / 1000.0
                        if message.alt is not None
                        else None
                    ),

                    delta_altitude_m=(
                        message.relative_alt / 1000.0
                        if message.relative_alt is not None
                        else None
                    ),

                    source_platform=self.platform_name,

                    raw={
                        "mavpackettype": "GLOBAL_POSITION_INT",
                        "time_boot_ms": message.time_boot_ms,
                        "lat": message.lat,
                        "lon": message.lon,
                        "alt": message.alt,
                        "relative_alt": message.relative_alt,
                        "vx": message.vx,
                        "vy": message.vy,
                        "vz": message.vz,
                        "hdg": message.hdg,
                        "mavlink_version": record[
                            "mavlink_version"
                        ],
                        "timestamp_us": record[
                            "timestamp_us"
                        ],
                    },
                )
            )

        return navigation_records

    def extract_battery(self):
        """
        Extract BATTERY_STATUS MAVLink messages into
        normalized BatteryRecord objects.
        """

        battery_records = []

        for record in self._iter_tlog():

            message = record["message"]

            if message.get_type() != "BATTERY_STATUS":
                continue

            raw = message.to_dict()

            # --------------------------------------------------
            # Temperature
            # --------------------------------------------------

            temperature_c = None

            if message.temperature is not None:
                temperature_c = (
                    message.temperature / 100.0
                )

            # --------------------------------------------------
            # Cell voltages
            # --------------------------------------------------

            cell_voltages_v = []

            for voltage_mv in message.voltages:

                if voltage_mv == 65535:
                    continue

                cell_voltages_v.append(
                    voltage_mv / 1000.0
                )

            cell_count = len(
                cell_voltages_v
            )

            max_cell_voltage_delta_v = None

            if cell_voltages_v:
                max_cell_voltage_delta_v = (
                    max(cell_voltages_v)
                    - min(cell_voltages_v)
                )

            # --------------------------------------------------
            # Current
            # --------------------------------------------------

            current_a = None

            if (
                message.current_battery is not None
                and message.current_battery != -1
            ):
                current_a = (
                    message.current_battery / 100.0
                )

            # --------------------------------------------------
            # Consumed capacity
            # --------------------------------------------------

            discharged_mah = None

            if (
                message.current_consumed is not None
                and message.current_consumed != -1
            ):
                discharged_mah = float(
                    message.current_consumed
                )

            # --------------------------------------------------
            # Remaining battery
            # --------------------------------------------------

            remaining = None

            if (
                message.battery_remaining is not None
                and message.battery_remaining >= 0
            ):
                remaining = (
                    message.battery_remaining / 100.0
                )

            battery_records.append(
                BatteryRecord(
                    timestamp=record["timestamp"],

                    voltage_v=(
                        sum(cell_voltages_v)
                        if cell_voltages_v
                        else None
                    ),

                    current_a=current_a,

                    discharged_mah=discharged_mah,

                    remaining=remaining,

                    temperature_c=temperature_c,

                    cell_count=cell_count,

                    cell_voltages_v=cell_voltages_v,

                    max_cell_voltage_delta_v=(
                        max_cell_voltage_delta_v
                    ),

                    source_platform=self.platform_name,

                    raw={
                        "mavpackettype": (
                            "BATTERY_STATUS"
                        ),
                        "mavlink_version": (
                            record["mavlink_version"]
                        ),
                        "timestamp_us": (
                            record["timestamp_us"]
                        ),
                        "packet_offset": (
                            record["packet_offset"]
                        ),
                        "message": raw,
                    },
                )
            )

        return battery_records

    def extract_telemetry(self):
        """Extract normalized MAVLink telemetry records."""
        return extract_mavlink_telemetry(
            self._iter_tlog(),
            self.platform_name,
        )

    def extract_failsafe(self):
        """Extract explicitly logged failsafe information."""
        return extract_mavlink_failsafe(
            self._iter_tlog(),
            self.platform_name,
        )

    def extract_commands(self):
        """Extract COMMAND_LONG and COMMAND_INT records."""
        return extract_mavlink_commands(
            self._iter_tlog(),
            self.platform_name,
        )

    def extract_command_acks(self):
        """Extract COMMAND_ACK records."""
        return extract_mavlink_command_acks(
            self._iter_tlog(),
            self.platform_name,
        )

    def extract_states(self):
        """Extract vehicle state records."""
        return extract_mavlink_states(
            self._iter_tlog(),
            self.platform_name,
        )

    def extract_parameters(self):
        """Extract PARAM_VALUE and PARAM_SET records."""
        return extract_mavlink_parameters(
            self._iter_tlog(),
            self.platform_name,
        )

    def extract_events(self):
        """Extract STATUSTEXT forensic events."""
        return extract_mavlink_events(
            self._iter_tlog(),
            self.platform_name,
        )

    def parse(self):
        """Build complete normalized evidence from the ArduPilot TLOG."""

        return NormalizedEvidence(
            metadata=self.get_metadata(),
            gps=self.extract_gps(),
            navigation=self.extract_navigation(),
            battery=self.extract_battery(),
            telemetry=self.extract_telemetry(),
            failsafe=self.extract_failsafe(),
            commands=self.extract_commands(),
            command_acks=self.extract_command_acks(),
            states=self.extract_states(),
            parameters=self.extract_parameters(),
            events=self.extract_events(),
        )

