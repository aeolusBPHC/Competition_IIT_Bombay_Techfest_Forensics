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


class MAVLinkTLogParser(BaseForensicParser):
    """
    Generic MAVLink TLOG forensic parser.

    Current scope:
    - TLOG structural detection
    - MAVLink version detection
    - MAVLink message extraction
    - GPS extraction
    - Normalized GPS evidence

    Supported GPS messages:
    - GPS_RAW_INT
    - GLOBAL_POSITION_INT
    """

    platform_name = "MAVLink"

    supported_formats = [
        "TLOG",
        ".tlog",
    ]

    TIMESTAMP_SIZE = 8

    @classmethod
    def identify(cls, evidence_path):
        """
        Identify whether the evidence file has a valid MAVLink
        TLOG structure.
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

            if not result["valid"]:
                return {
                    "supported": False,
                    "platform": cls.platform_name,
                    "format": None,
                    "confidence": "NONE",
                    "reason": result["reason"],
                }

            return {
                "supported": True,
                "platform": cls.platform_name,
                "format": "TLOG",
                "confidence": "LOW",
                "reason": (
                    "Generic MAVLink TLOG structure detected; "
                    "flight-controller platform not yet resolved"
                ),
                "indicators": result["indicators"],
            }

        except Exception as exc:
            return {
                "supported": False,
                "platform": cls.platform_name,
                "format": None,
                "confidence": "ERROR",
                "reason": (
                    f"MAVLink TLOG validation failed: {exc}"
                ),
            }

    @classmethod
    def _inspect_tlog(cls, path):
        """
        Inspect the first part of a TLOG file.

        This is used only for format detection and does not
        parse the complete evidence file.
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
            }

        try:
            records = list(
                cls._iter_tlog_bytes(
                    data,
                    max_records=None,
                )
            )

        except Exception as exc:
            return {
                "valid": False,
                "reason": f"TLOG parsing failed: {exc}",
                "indicators": {},
            }

        if not records:
            return {
                "valid": False,
                "reason": (
                    "No valid MAVLink records detected"
                ),
                "indicators": {},
            }

        mavlink_versions = set()
        message_types = []

        for record in records:

            mavlink_versions.add(
                record["mavlink_version"]
            )

            message_types.append(
                record["message"].get_type()
            )

        return {
            "valid": True,
            "reason": "Valid MAVLink records detected",
            "indicators": {
                "records_detected": len(records),
                "mavlink_versions": sorted(
                    mavlink_versions
                ),
                "message_types": message_types,
            },
        }

    @classmethod
    def _iter_tlog_bytes(
        cls,
        data,
        max_records=None,
    ):
        """
        Iterate over TLOG records.

        TLOG structure:

            8-byte big-endian timestamp
            MAVLink packet

        MAVLink packets can use:

            MAVLink 1 -> 0xFE
            MAVLink 2 -> 0xFD
        """

        try:
            from pymavlink import mavutil

        except ImportError as exc:
            raise RuntimeError(
                "pymavlink is not installed"
            ) from exc

        offset = 0
        records = 0

        while (
            offset + cls.TIMESTAMP_SIZE
            <= len(data)
        ):

            timestamp_offset = offset

            timestamp_us = struct.unpack(
                ">Q",
                data[
                    offset:
                    offset + cls.TIMESTAMP_SIZE
                ],
            )[0]

            offset += cls.TIMESTAMP_SIZE

            if offset >= len(data):
                break

            magic = data[offset]

            if magic not in (0xFE, 0xFD):
                raise ValueError(
                    "Invalid MAVLink magic byte at "
                    f"offset {offset}: "
                    f"0x{magic:02x}"
                )

            if offset + 2 > len(data):
                raise ValueError(
                    "Incomplete MAVLink header"
                )

            payload_length = data[offset + 1]

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

                incompat_flags = data[offset + 2]

                # MAVLink 2 signing adds a 13-byte signature.
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

            records += 1

            offset = packet_end

            if (
                max_records is not None
                and records >= max_records
            ):
                break

    def _iter_tlog(self):
        """
        Iterate over all TLOG records.

        The complete evidence file is loaded for the current
        PoC implementation.

        Later this can be replaced with streaming/chunked
        processing for very large TLOG files.
        """

        data = self.evidence_path.read_bytes()

        yield from self._iter_tlog_bytes(
            data
        )

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

        1. GPS_RAW_INT
           - Raw GPS measurements
           - Latitude/longitude: degrees * 1e7
           - Altitude: millimeters
           - Velocity: centimeters/second
           - Heading: centidegrees
           - HDOP/VDOP: value * 0.01

        2. GLOBAL_POSITION_INT
           - Filtered/global vehicle position
           - Latitude/longitude: degrees * 1e7
           - Altitude: millimeters
           - VX/VY: centimeters/second
           - Heading: centidegrees
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

                # 65535 means heading unavailable.
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

        GLOBAL_POSITION_INT provides the filtered/global
        vehicle position estimate.

        Normalization:
        - lat / 1e7 -> degrees
        - lon / 1e7 -> degrees
        - alt / 1000 -> meters
        - relative_alt / 1000 -> meters above home

        The outer TLOG timestamp is used as the
        forensic timestamp.
        """

        navigation_records = []

        for record in self._iter_tlog():

            message = record["message"]

            if message.get_type() != "GLOBAL_POSITION_INT":
                continue

            raw = message.to_dict()

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

                    raw=raw,
                )
            )

        return navigation_records

    def extract_battery(self):
        """
        Extract BATTERY_STATUS MAVLink messages into
        normalized BatteryRecord objects.

        MAVLink BATTERY_STATUS units:

        temperature:
            centi-degrees Celsius

        voltages:
            millivolts per cell

        current_battery:
            centi-amperes

        current_consumed:
            milliampere-hours

        battery_remaining:
            percentage
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

                # MAVLink UINT16_MAX means invalid/unavailable.
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
                discharged_mah = (
                    float(message.current_consumed)
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
        """Build complete normalized evidence from the MAVLink TLOG."""

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

