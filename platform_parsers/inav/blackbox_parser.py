from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_parsers.common.base_parser import BaseForensicParser
from platform_parsers.common.evidence_model import (
    EvidenceMetadata,
    GPSRecord,
    NavigationRecord,
    NormalizedEvidence,
)


@dataclass
class _BlackboxField:
    name: str
    signed: bool
    predictor: str
    encoding: str


class INAVBlackboxParser(BaseForensicParser):
    """
    INAV Blackbox forensic parser.

    Current scope:
        - Blackbox identification
        - header extraction
        - metadata normalization
        - GPS H/home frame decoding
        - GPS G frame decoding
        - HOME_COORD reconstruction
        - GPS unit normalization
        - raw GPS value preservation

    The parser deliberately refuses unsupported encodings or frame
    types instead of guessing byte offsets.
    """

    platform_name = "INAV"

    supported_formats = [
        "BLACKBOX",
        ".bbl",
        ".TXT",
    ]

    BLACKBOX_MARKER = (
        b"H Product:Blackbox flight data recorder by Nicholas Sherlock\n"
    )

    GPS_FRAME = ord("G")
    HOME_FRAME = ord("H")

    # INAV Blackbox predictor identifiers.
    PREDICTOR_ZERO = "0"
    PREDICTOR_LAST = "1"
    PREDICTOR_STRAIGHT_LINE = "2"
    PREDICTOR_AVERAGE_2 = "3"
    PREDICTOR_MINTHROTTLE = "4"
    PREDICTOR_MOTOR_0 = "5"
    PREDICTOR_INCREMENT = "6"
    PREDICTOR_HOME_COORD = "7"
    PREDICTOR_1500 = "8"
    PREDICTOR_VBATREF = "9"
    PREDICTOR_LAST_MAIN_FRAME_TIME = "10"

    # INAV Blackbox encoder identifiers.
    ENCODING_SIGNED_VB = "0"
    ENCODING_UNSIGNED_VB = "1"

    @classmethod
    def identify(cls, evidence_path):
        path = Path(evidence_path)

        if not path.exists():
            raise FileNotFoundError(
                f"Evidence file does not exist: {path}"
            )

        if not path.is_file():
            raise ValueError(
                f"Evidence path is not a file: {path}"
            )

        try:
            with path.open("rb") as file:
                data = file.read(256 * 1024)

            marker_index = data.find(cls.BLACKBOX_MARKER)

            if marker_index == -1:
                return {
                    "supported": False,
                    "platform": cls.platform_name,
                    "format": None,
                    "confidence": "NONE",
                    "reason": (
                        "INAV Blackbox product header not detected"
                    ),
                    "indicators": {},
                }

            headers = cls._parse_headers(
                data[marker_index:]
            )

            firmware_type = headers.get(
                "Firmware type",
                "",
            )

            data_version = headers.get(
                "Data version"
            )

            if firmware_type:
                firmware_lower = firmware_type.lower()

                if "inav" not in firmware_lower:
                    return {
                        "supported": False,
                        "platform": cls.platform_name,
                        "format": None,
                        "confidence": "NONE",
                        "reason": (
                            "Blackbox log belongs to a different "
                            f"firmware platform: {firmware_type}"
                        ),
                        "indicators": {
                            "marker_detected": True,
                            "firmware_type": firmware_type,
                            "data_version": data_version,
                        },
                    }

                confidence = "HIGH"

            else:
                return {
                    "supported": False,
                    "platform": cls.platform_name,
                    "format": None,
                    "confidence": "NONE",
                    "reason": (
                        "INAV Blackbox header detected but firmware "
                        "type is unavailable"
                    ),
                    "indicators": {
                        "marker_detected": True,
                        "firmware_type": None,
                        "data_version": data_version,
                    },
                }

            return {
                "supported": True,
                "platform": cls.platform_name,
                "format": "BLACKBOX",
                "confidence": confidence,
                "reason": "Blackbox flight log structure detected",
                "indicators": {
                    "marker_detected": True,
                    "firmware_type": firmware_type or None,
                    "data_version": data_version,
                },
            }

        except Exception as exc:
            return {
                "supported": False,
                "platform": cls.platform_name,
                "format": None,
                "confidence": "ERROR",
                "reason": str(exc),
            }

    # ---------------------------------------------------------------
    # Header parsing
    # ---------------------------------------------------------------

    @staticmethod
    def _parse_headers(data: bytes) -> dict[str, str]:
        headers: dict[str, str] = {}

        for line in data.splitlines():
            if not line.startswith(b"H "):
                break

            text = line.decode(
                "ascii",
                errors="replace",
            )

            text = text[2:]

            if ":" not in text:
                continue

            name, value = text.split(
                ":",
                1,
            )

            headers[name.strip()] = value.strip()

        return headers

    def _load_raw_header(self) -> bytes:
        with self.evidence_path.open("rb") as file:
            data = file.read(512 * 1024)

        marker_index = data.find(
            self.BLACKBOX_MARKER
        )

        if marker_index == -1:
            return b""

        return data[marker_index:]

    # ---------------------------------------------------------------
    # Field-header parsing
    # ---------------------------------------------------------------

    def _parse_field_headers(
        self,
        frame_type: str,
    ) -> list[_BlackboxField]:

        data = self._load_raw_header()

        if not data:
            return []

        values: dict[str, list[str]] = {}

        prefix = f"H Field {frame_type} "

        for raw_line in data.splitlines():
            line = raw_line.decode(
                "ascii",
                errors="replace",
            )

            if not line.startswith(prefix):
                continue

            remainder = line[len(prefix):]

            if ":" in remainder:
                key, value = remainder.split(
                    ":",
                    1,
                )
            elif "=" in remainder:
                key, value = remainder.split(
                    "=",
                    1,
                )
            else:
                continue

            key = key.strip().lower()

            values[key] = [
                item.strip()
                for item in value.split(",")
            ]

        names = values.get("name", [])
        signed_values = values.get("signed", [])
        predictors = values.get("predictor", [])
        encodings = values.get("encoding", [])

        if not names:
            return []

        fields: list[_BlackboxField] = []

        for index, name in enumerate(names):

            signed = False

            if index < len(signed_values):
                signed = (
                    signed_values[index].strip()
                    in {
                        "1",
                        "S",
                        "SIGNED",
                        "true",
                        "True",
                    }
                )

            predictor = (
                predictors[index]
                if index < len(predictors)
                else self.PREDICTOR_ZERO
            )

            encoding = (
                encodings[index]
                if index < len(encodings)
                else (
                    self.ENCODING_SIGNED_VB
                    if signed
                    else self.ENCODING_UNSIGNED_VB
                )
            )

            fields.append(
                _BlackboxField(
                    name=name,
                    signed=signed,
                    predictor=predictor,
                    encoding=encoding,
                )
            )

        return fields

    # ---------------------------------------------------------------
    # Variable-byte decoding
    # ---------------------------------------------------------------

    @staticmethod
    def _read_unsigned_vb(
        data: bytes,
        offset: int,
    ) -> tuple[int, int]:

        value = 0
        shift = 0

        while True:

            if offset >= len(data):
                raise ValueError(
                    "Unexpected end of data while decoding "
                    "UNSIGNED_VB"
                )

            byte = data[offset]
            offset += 1

            value |= (
                byte & 0x7F
            ) << shift

            if not (
                byte & 0x80
            ):
                return value, offset

            shift += 7

            if shift > 63:
                raise ValueError(
                    "UNSIGNED_VB value exceeds supported size"
                )

    @classmethod
    def _read_signed_vb(
        cls,
        data: bytes,
        offset: int,
    ) -> tuple[int, int]:

        unsigned, offset = (
            cls._read_unsigned_vb(
                data,
                offset,
            )
        )

        # ZigZag decoding.
        value = unsigned >> 1

        if unsigned & 1:
            value = -value - 1

        return value, offset

    # ---------------------------------------------------------------
    # Field decoding
    # ---------------------------------------------------------------

    @classmethod
    def _decode_value(
        cls,
        data: bytes,
        offset: int,
        field: _BlackboxField,
    ) -> tuple[int, int]:

        encoding = field.encoding.strip()

        if encoding in {
            cls.ENCODING_UNSIGNED_VB,
            "UNSIGNED_VB",
            "unsigned_vb",
        }:
            return cls._read_unsigned_vb(
                data,
                offset,
            )

        if encoding in {
            cls.ENCODING_SIGNED_VB,
            "SIGNED_VB",
            "signed_vb",
        }:
            return cls._read_signed_vb(
                data,
                offset,
            )

        raise NotImplementedError(
            "Unsupported INAV Blackbox encoding: "
            f"{field.encoding}"
        )

    # ---------------------------------------------------------------
    # Home frame
    # ---------------------------------------------------------------

    @classmethod
    def _decode_home_frame(
        cls,
        data: bytes,
        offset: int,
        fields: list[_BlackboxField],
    ) -> tuple[dict[str, Any], int]:

        values: dict[str, Any] = {}

        for field in fields:

            value, offset = (
                cls._decode_value(
                    data,
                    offset,
                    field,
                )
            )

            values[field.name] = value

        return values, offset

    # ---------------------------------------------------------------
    # GPS frame
    # ---------------------------------------------------------------

    @classmethod
    def _decode_gps_frame(
        cls,
        data: bytes,
        offset: int,
        fields: list[_BlackboxField],
        home: dict[int, int],
    ) -> tuple[dict[str, Any], int]:

        values: dict[str, Any] = {}

        for field in fields:

            value, offset = (
                cls._decode_value(
                    data,
                    offset,
                    field,
                )
            )

            name = field.name

            if (
                field.predictor
                in {
                    cls.PREDICTOR_HOME_COORD,
                    "HOME_COORD",
                    "7",
                }
            ):

                if name in {
                    "GPS_coord[0]",
                    "GPS_coord[1]",
                }:

                    index = (
                        0
                        if name.endswith("[0]")
                        else 1
                    )

                    value += home.get(
                        index,
                        0,
                    )

            values[name] = value

        return values, offset

    # ---------------------------------------------------------------
    # Locate payload
    # ---------------------------------------------------------------

    @staticmethod
    def _find_data_start(
        data: bytes,
    ) -> int | None:

        position = 0

        for line in data.splitlines(
            keepends=True
        ):

            if not line.startswith(b"H "):
                break

            position += len(line)

        if position >= len(data):
            return None

        return position

    # ---------------------------------------------------------------
    # GPS frame iterator
    # ---------------------------------------------------------------

    def _iter_gps_frames(self):

        raw = self._load_raw_header()

        if not raw:
            return

        header_end = (
            self._find_data_start(raw)
        )

        if header_end is None:
            return

        data = raw[header_end:]

        gps_fields = (
            self._parse_field_headers("G")
        )

        home_fields = (
            self._parse_field_headers("H")
        )

        if not gps_fields:
            return

        home: dict[int, int] = {}

        offset = 0

        while offset < len(data):

            frame_type = data[offset]
            offset += 1

            # -------------------------------------------------------
            # H = GPS home/reference frame
            # -------------------------------------------------------

            if frame_type == self.HOME_FRAME:

                if not home_fields:
                    raise ValueError(
                        "H frame encountered but no H field "
                        "definitions were found"
                    )

                values, offset = (
                    self._decode_home_frame(
                        data,
                        offset,
                        home_fields,
                    )
                )

                for name, value in values.items():

                    if name == "GPS_home[0]":
                        home[0] = value

                    elif name == "GPS_home[1]":
                        home[1] = value

                yield {
                    "frame_type": "H",
                    "values": values,
                    "raw_offset": offset,
                }

                continue

            # -------------------------------------------------------
            # G = GPS frame
            # -------------------------------------------------------

            if frame_type == self.GPS_FRAME:

                values, offset = (
                    self._decode_gps_frame(
                        data,
                        offset,
                        gps_fields,
                        home,
                    )
                )

                yield {
                    "frame_type": "G",
                    "values": values,
                    "raw_offset": offset,
                }

                continue

            # -------------------------------------------------------
            # We intentionally refuse to guess around other frames.
            # -------------------------------------------------------

            raise NotImplementedError(
                "Encountered INAV Blackbox frame "
                f"{chr(frame_type)!r}. "
                "Full I/P/S/E decoding is not yet implemented; "
                "refusing to guess GPS offsets."
            )

    # ---------------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------------

    def get_metadata(self):

        headers = self._parse_headers(
            self._load_raw_header()
        )

        firmware = headers.get(
            "Firmware type"
        )

        firmware_version = headers.get(
            "Firmware revision"
        )

        return EvidenceMetadata(
            source_file=str(
                self.evidence_path
            ),
            platform=self.platform_name,
            format="BLACKBOX",
            firmware=firmware,
            firmware_version=firmware_version,
            metadata={
                "blackbox_headers": headers,
                "gps_fields": [
                    field.name
                    for field in (
                        self._parse_field_headers(
                            "G"
                        )
                    )
                ],
                "home_fields": [
                    field.name
                    for field in (
                        self._parse_field_headers(
                            "H"
                        )
                    )
                ],
            },
        )

    # ---------------------------------------------------------------
    # GPS extraction
    # ---------------------------------------------------------------

    def extract_gps(self):

        records: list[GPSRecord] = []

        for frame in (
            self._iter_gps_frames()
            or []
        ):

            if frame["frame_type"] != "G":
                continue

            values = frame["values"]

            # INAV's GPS time is in milliseconds/UTC-style GPS time,
            # while the Blackbox "time" field is the flight-controller
            # timestamp. Prefer "time" when available.
            timestamp_raw = values.get(
                "time"
            )

            if timestamp_raw is None:
                timestamp = 0.0
            else:
                timestamp = (
                    timestamp_raw
                    / 1_000_000.0
                )

            latitude_raw = values.get(
                "GPS_coord[0]"
            )

            longitude_raw = values.get(
                "GPS_coord[1]"
            )

            latitude = (
                latitude_raw / 10_000_000.0
                if latitude_raw is not None
                else None
            )

            longitude = (
                longitude_raw / 10_000_000.0
                if longitude_raw is not None
                else None
            )

            altitude_raw = values.get(
                "GPS_altitude"
            )

            altitude = (
                float(altitude_raw)
                if altitude_raw is not None
                else None
            )

            speed_raw = values.get(
                "GPS_speed"
            )

            speed = (
                speed_raw / 100.0
                if speed_raw is not None
                else None
            )

            course_raw = values.get(
                "GPS_ground_course"
            )

            heading = (
                course_raw / 10.0
                if course_raw is not None
                else None
            )

            records.append(
                GPSRecord(
                    timestamp=timestamp,
                    latitude=latitude,
                    longitude=longitude,
                    altitude_m=altitude,
                    speed_m_s=speed,
                    fix_type=values.get(
                        "GPS_fixType"
                    ),
                    satellites=values.get(
                        "GPS_numSat"
                    ),
                    hdop=values.get(
                        "GPS_hdop"
                    ),
                    vdop=None,
                    heading_deg=heading,
                    jamming_state=None,
                    spoofing_state=None,
                    source_platform=self.platform_name,
                    raw=values.copy(),
                )
            )

        return records

    # ---------------------------------------------------------------
    # Navigation extraction
    # ---------------------------------------------------------------

    def extract_navigation(self):

        records: list[NavigationRecord] = []

        for frame in (
            self._iter_gps_frames()
            or []
        ):

            if frame["frame_type"] != "G":
                continue

            values = frame["values"]

            timestamp_raw = values.get(
                "time"
            )

            if timestamp_raw is None:
                timestamp = 0.0
            else:
                timestamp = (
                    timestamp_raw
                    / 1_000_000.0
                )

            latitude_raw = values.get(
                "GPS_coord[0]"
            )

            longitude_raw = values.get(
                "GPS_coord[1]"
            )

            latitude = (
                latitude_raw / 10_000_000.0
                if latitude_raw is not None
                else None
            )

            longitude = (
                longitude_raw / 10_000_000.0
                if longitude_raw is not None
                else None
            )

            altitude_raw = values.get(
                "GPS_altitude"
            )

            altitude = (
                float(altitude_raw)
                if altitude_raw is not None
                else None
            )

            records.append(
                NavigationRecord(
                    timestamp=timestamp,

                    latitude=latitude,

                    longitude=longitude,

                    altitude_m=altitude,

                    delta_altitude_m=None,

                    source_platform=(
                        self.platform_name
                    ),

                    raw={
                        "dataset": "G",

                        "time": timestamp_raw,

                        "GPS_fixType": values.get(
                            "GPS_fixType"
                        ),

                        "GPS_numSat": values.get(
                            "GPS_numSat"
                        ),

                        "GPS_coord[0]": latitude_raw,

                        "GPS_coord[1]": longitude_raw,

                        "GPS_altitude": altitude_raw,

                        "GPS_speed": values.get(
                            "GPS_speed"
                        ),

                        "GPS_ground_course": values.get(
                            "GPS_ground_course"
                        ),

                        "GPS_velned[0]": values.get(
                            "GPS_velned[0]"
                        ),

                        "GPS_velned[1]": values.get(
                            "GPS_velned[1]"
                        ),

                        "GPS_velned[2]": values.get(
                            "GPS_velned[2]"
                        ),

                        "GPS_time": values.get(
                            "GPS_time"
                        ),
                    },
                )
            )

        return records

    # ---------------------------------------------------------------
    # Normalized categories
    # ---------------------------------------------------------------

    def extract_battery(self):
        """
        Extract normalized battery records.

        INAV I-frame decoding is not currently implemented in this parser.
        Therefore battery records cannot be extracted reliably from the
        current implementation without guessing field offsets or meanings.
        """
        return []

    def extract_telemetry(self):
        """
        Extract normalized telemetry records.

        No telemetry/link-status dataset is currently decoded from the
        INAV Blackbox evidence.
        """
        return []

    def extract_failsafe(self):
        """
        Extract normalized failsafe records.

        Explicit failsafe records are not currently decoded from INAV
        Blackbox frames.
        """
        return []

    def extract_commands(self):
        """
        Extract normalized command records.

        Command/control records are not currently decoded from INAV
        Blackbox evidence.
        """
        return []

    def extract_command_acks(self):
        """
        Extract normalized command acknowledgement records.

        No native COMMAND_ACK-equivalent record is currently decoded.
        """
        return []

    def extract_states(self):
        """
        Extract normalized vehicle state records.

        INAV I/P/S/E frame decoding is not currently implemented, so state
        records are not inferred from GPS records.
        """
        return []

    def extract_parameters(self):
        """
        Extract normalized parameter records.

        Parameter records are not currently decoded from the Blackbox
        evidence.
        """
        return []

    def extract_events(self):
        """
        Extract normalized forensic events.

        INAV P/S/E frame decoding is not currently implemented, so forensic
        events are not synthesized.
        """
        return []

    def parse(self):
        """Build complete normalized evidence from the INAV Blackbox log."""

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
