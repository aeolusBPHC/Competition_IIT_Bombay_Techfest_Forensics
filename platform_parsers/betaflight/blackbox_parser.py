from dataclasses import dataclass
from pathlib import Path

from platform_parsers.common.base_parser import BaseForensicParser
from platform_parsers.common.evidence_model import (
    BatteryRecord,
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


class BetaflightBlackboxParser(BaseForensicParser):

    platform_name = "Betaflight"
    supported_formats = ["BLACKBOX"]

    @classmethod
    def identify(cls, evidence_path):
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
                "reason": "Path is not a file",
            }

        try:
            with path.open("rb") as handle:
                sample = handle.read(8192)

            text = sample.decode(
                "ascii",
                errors="ignore",
            )

            firmware_type = None
            data_version = None

            for line in text.splitlines():
                if line.startswith("H Firmware type:"):
                    firmware_type = (
                        line.split(":", 1)[1].strip()
                    )

                elif line.startswith("H Data version:"):
                    data_version = (
                        line.split(":", 1)[1].strip()
                    )

            marker_detected = (
                "H Product:Blackbox flight data recorder"
                in text
                and "H Data version:" in text
            )

            if not marker_detected:
                return {
                    "supported": False,
                    "platform": cls.platform_name,
                    "format": None,
                    "confidence": "NONE",
                    "reason": "Blackbox header not detected",
                    "indicators": {
                        "marker_detected": False,
                        "firmware_type": firmware_type,
                        "data_version": data_version,
                    },
                }

            # Blackbox is shared by multiple flight-controller
            # platforms. Do not claim evidence belonging to another
            # platform.
            if firmware_type is not None:
                if firmware_type.lower() != "betaflight":
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

                return {
                    "supported": True,
                    "platform": cls.platform_name,
                    "format": "BLACKBOX",
                    "confidence": "HIGH",
                    "reason": (
                        "Betaflight Blackbox header detected"
                    ),
                    "indicators": {
                        "marker_detected": True,
                        "firmware_type": firmware_type,
                        "data_version": data_version,
                    },
                }

            # No firmware type means the evidence cannot be reliably
            # attributed to Betaflight.
            return {
                "supported": False,
                "platform": cls.platform_name,
                "format": None,
                "confidence": "NONE",
                "reason": (
                    "Blackbox header detected but firmware "
                    "type is unavailable"
                ),
                "indicators": {
                    "marker_detected": True,
                    "firmware_type": None,
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

    # ------------------------------------------------------------------
    # Raw/header handling
    # ------------------------------------------------------------------

    def _load_raw_header(self):
        return self.evidence_path.read_bytes()

    def _find_data_start(self, raw):
        """
        Find the first byte after the textual Blackbox header.

        Header lines begin with 'H '.
        Blank lines are skipped.
        The first non-header, non-blank line marks binary data.
        """

        offset = 0

        while offset < len(raw):
            newline = raw.find(b"\n", offset)

            if newline == -1:
                return None

            line = raw[offset:newline]

            if line.startswith(b"H "):
                offset = newline + 1
                continue

            if line.strip() == b"":
                offset = newline + 1
                continue

            return offset

        return None

    def _parse_headers(self, raw):
        """
        Parse Blackbox textual headers.

        Supports both:

            H Key:Value

        and:

            H Field G name = ...

        """

        headers = {}

        for line in raw.splitlines():

            if not line.startswith(b"H "):
                continue

            text = line.decode(
                "ascii",
                errors="ignore",
            )[2:]

            # Field definitions use '='
            if "=" in text:
                key, value = text.split("=", 1)

                headers[key.strip()] = value.strip()
                continue

            # Normal Blackbox headers use ':'
            if ":" in text:
                key, value = text.split(":", 1)

                headers[key.strip()] = value.strip()

        return headers

    def _parse_field_headers(self, frame_type):
        """
        Parse:

            H Field G name = ...
            H Field G signed = ...
            H Field G predictor = ...
            H Field G encoding = ...

        """

        raw = self._load_raw_header()
        headers = self._parse_headers(raw)

        prefix = f"Field {frame_type} "

        names = None
        signed = None
        predictors = None
        encodings = None

        for key, value in headers.items():

            if not key.startswith(prefix):
                continue

            field_name = key[len(prefix):].strip()

            values = [
                item.strip()
                for item in value.split(",")
            ]

            if field_name == "name":
                names = values

            elif field_name == "signed":
                signed = values

            elif field_name == "predictor":
                predictors = values

            elif field_name == "encoding":
                encodings = values

        if not names:
            return []

        signed = signed or ["0"] * len(names)
        predictors = predictors or ["0"] * len(names)
        encodings = encodings or ["0"] * len(names)

        fields = []

        for index, name in enumerate(names):

            fields.append(
                _BlackboxField(
                    name=name,
                    signed=str(signed[index]).upper()
                    in {"1", "S", "SIGNED"},
                    predictor=str(predictors[index]),
                    encoding=str(encodings[index]),
                )
            )

        return fields

    # ------------------------------------------------------------------
    # Variable-byte decoding
    # ------------------------------------------------------------------

    @staticmethod
    def _read_unsigned_vb(data, offset):

        result = 0
        shift = 0

        while offset < len(data):

            byte = data[offset]
            offset += 1

            result |= (
                (byte & 0x7F)
                << shift
            )

            if not (byte & 0x80):
                return result, offset

            shift += 7

        raise ValueError(
            "Unexpected end of data while decoding "
            "unsigned variable-byte integer"
        )

    @staticmethod
    def _read_signed_vb(data, offset):

        value, offset = (
            BetaflightBlackboxParser
            ._read_unsigned_vb(
                data,
                offset,
            )
        )

        if value & 1:
            value = -(value >> 1) - 1

        else:
            value >>= 1

        return value, offset

    @classmethod
    def _decode_value(
        cls,
        data,
        offset,
        field,
    ):

        encoding = field.encoding.upper()

        if encoding in {
            "UNSIGNED_VB",
            "1",
            "UNSIGNED",
        }:

            return cls._read_unsigned_vb(
                data,
                offset,
            )

        if encoding in {
            "SIGNED_VB",
            "0",
            "SIGNED",
        }:

            return cls._read_signed_vb(
                data,
                offset,
            )

        if encoding in {
            "NEG_14BIT",
            "2",
        }:

            value, offset = (
                cls._read_unsigned_vb(
                    data,
                    offset,
                )
            )

            value &= 0x3FFF

            return value, offset

        raise NotImplementedError(
            f"Unsupported Blackbox encoding "
            f"'{field.encoding}' for field "
            f"'{field.name}'"
        )

    # ------------------------------------------------------------------
    # Frame decoding
    # ------------------------------------------------------------------

    @classmethod
    def _decode_home_frame(
        cls,
        data,
        offset,
        fields,
    ):

        values = {}

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

    @classmethod
    def _decode_gps_frame(
        cls,
        data,
        offset,
        fields,
        previous,
        home,
    ):

        values = {}

        for field in fields:

            value, offset = (
                cls._decode_value(
                    data,
                    offset,
                    field,
                )
            )

            predictor = field.predictor.upper()

            # ----------------------------------------------------------
            # HOME_COORD predictor
            #
            # Blackbox stores GPS coordinates relative to:
            #
            #   GPS_home[0] -> latitude
            #   GPS_home[1] -> longitude
            #
            # while the G frame fields are:
            #
            #   GPS_coord[0]
            #   GPS_coord[1]
            # ----------------------------------------------------------

            if predictor == "HOME_COORD":

                if field.name == "GPS_coord[0]":

                    home_value = home.get(
                        "GPS_home[0]",
                        0,
                    )

                elif field.name == "GPS_coord[1]":

                    home_value = home.get(
                        "GPS_home[1]",
                        0,
                    )

                else:

                    home_value = 0

                value = (
                    home_value
                    + value
                )

            values[field.name] = value

        return values, offset

    @classmethod
    def _decode_main_frame(
        cls,
        data,
        offset,
        fields,
        headers,
    ):

        values = {}

        try:

            vbatref = int(
                headers.get(
                    "vbatref",
                    headers.get(
                        "vbat_ref",
                        "0",
                    ),
                )
            )

        except ValueError:

            vbatref = 0

        for field in fields:

            value, offset = (
                cls._decode_value(
                    data,
                    offset,
                    field,
                )
            )

            predictor = field.predictor.upper()

            if predictor in {
                "VBATREF",
                "9",
            }:

                value = (
                    vbatref
                    - value
                )

            values[field.name] = value

        return values, offset

    # ------------------------------------------------------------------
    # GPS frame iterator
    # ------------------------------------------------------------------

    def _iter_gps_frames(self):

        raw = self._load_raw_header()

        if not raw:
            return

        data_start = (
            self._find_data_start(raw)
        )

        if data_start is None:
            return

        data = raw[data_start:]

        home_fields = (
            self._parse_field_headers("H")
        )

        gps_fields = (
            self._parse_field_headers("G")
        )

        offset = 0

        previous = {}
        home = {}

        while offset < len(data):

            frame_offset = offset

            frame_type = data[offset]

            offset += 1

            # ----------------------------------------------------------
            # Home frame
            # ----------------------------------------------------------

            if frame_type == ord("H"):

                values, offset = (
                    self._decode_home_frame(
                        data,
                        offset,
                        home_fields,
                    )
                )

                home.update(values)

                continue

            # ----------------------------------------------------------
            # GPS frame
            # ----------------------------------------------------------

            if frame_type == ord("G"):

                values, offset = (
                    self._decode_gps_frame(
                        data,
                        offset,
                        gps_fields,
                        previous,
                        home,
                    )
                )

                previous.update(values)

                yield {
                    "frame_type": "G",
                    "values": values,
                    "raw_offset": frame_offset,
                }

                continue

            # ----------------------------------------------------------
            # I frame marks main flight data
            # ----------------------------------------------------------

            if frame_type == ord("I"):

                break

            # ----------------------------------------------------------
            # Other Blackbox frame types
            # ----------------------------------------------------------

            if frame_type in {
                ord("P"),
                ord("S"),
                ord("E"),
            }:

                raise NotImplementedError(
                    f"Encountered Blackbox frame "
                    f"'{chr(frame_type)}'. "
                    f"Full P/S/E decoding is not yet "
                    f"implemented; refusing to guess "
                    f"main-frame offsets."
                )

            raise ValueError(
                f"Unknown Blackbox frame type "
                f"0x{frame_type:02X} "
                f"at offset {frame_offset}"
            )

    # ------------------------------------------------------------------
    # Main frame iterator
    # ------------------------------------------------------------------

    def _iter_main_frames(self):

        raw = self._load_raw_header()

        if not raw:
            return

        header_end = (
            self._find_data_start(raw)
        )

        if header_end is None:
            return

        data = raw[header_end:]

        main_fields = (
            self._parse_field_headers("I")
        )

        if not main_fields:
            return

        headers = self._parse_headers(raw)

        home_fields = (
            self._parse_field_headers("H")
        )

        gps_fields = (
            self._parse_field_headers("G")
        )

        offset = 0

        previous = {}
        home = {}

        while offset < len(data):

            frame_offset = offset

            frame_type = data[offset]

            offset += 1

            # ----------------------------------------------------------
            # Home frame
            # ----------------------------------------------------------

            if frame_type == ord("H"):

                values, offset = (
                    self._decode_home_frame(
                        data,
                        offset,
                        home_fields,
                    )
                )

                home.update(values)

                continue

            # ----------------------------------------------------------
            # GPS frame
            # ----------------------------------------------------------

            if frame_type == ord("G"):

                values, offset = (
                    self._decode_gps_frame(
                        data,
                        offset,
                        gps_fields,
                        previous,
                        home,
                    )
                )

                previous.update(values)

                continue

            # ----------------------------------------------------------
            # Main/I frame
            # ----------------------------------------------------------

            if frame_type == ord("I"):

                values, offset = (
                    self._decode_main_frame(
                        data,
                        offset,
                        main_fields,
                        headers,
                    )
                )

                yield {
                    "frame_type": "I",
                    "values": values,
                    "raw_offset": frame_offset,
                }

                continue

            # ----------------------------------------------------------
            # Other frame types
            # ----------------------------------------------------------

            if frame_type in {
                ord("P"),
                ord("S"),
                ord("E"),
            }:

                raise NotImplementedError(
                    f"Encountered Blackbox frame "
                    f"'{chr(frame_type)}'. "
                    f"Full P/S/E decoding is not yet "
                    f"implemented; refusing to guess "
                    f"main-frame offsets."
                )

            raise ValueError(
                f"Unknown Blackbox frame type "
                f"0x{frame_type:02X} "
                f"at offset {frame_offset}"
            )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_metadata(self):
        raw = self._load_raw_header()
        headers = self._parse_headers(raw)

        firmware = headers.get("Firmware type")
        firmware_version = headers.get("Firmware revision")

        gps_fields = self._parse_field_headers("G")
        battery_fields = self._parse_field_headers("I")
        home_fields = self._parse_field_headers("H")

        return EvidenceMetadata(
            source_file=self.evidence_path.name,
            platform=self.platform_name,
            format="BLACKBOX",
            firmware=firmware,
            firmware_version=firmware_version,
            metadata={
                "product": headers.get("Product"),
                "data_version": headers.get("Data version"),
                "firmware_type": firmware,
                "firmware_revision": firmware_version,
                "firmware_date": headers.get("Firmware date"),
                "firmware_time": headers.get("Firmware time"),

                # Parsed field definitions
                "gps_fields": [
                    field.name
                    for field in gps_fields
                ],

                "battery_fields": [
                    field.name
                    for field in battery_fields
                ],

                "home_fields": [
                    field.name
                    for field in home_fields
                 ],

                 # Preserve all original Blackbox headers
                 "headers": headers,
            },
       )

    # ------------------------------------------------------------------
    # GPS extraction
    # ------------------------------------------------------------------

    def extract_gps(self):

        records = []

        for frame in self._iter_gps_frames():

            values = frame["values"]

            timestamp = (
                values.get(
                    "time",
                    0,
                )
                / 1_000_000.0
            )

            latitude_raw = values.get(
                "GPS_coord[0]"
            )

            longitude_raw = values.get(
                "GPS_coord[1]"
            )

            altitude_raw = values.get(
                "GPS_altitude"
            )

            speed_raw = values.get(
                "GPS_speed"
            )

            course_raw = values.get(
                "GPS_ground_course"
            )

            latitude = (
                latitude_raw
                / 10_000_000.0
                if latitude_raw is not None
                else None
            )

            longitude = (
                longitude_raw
                / 10_000_000.0
                if longitude_raw is not None
                else None
            )

            altitude = (
                altitude_raw
                / 10.0
                if altitude_raw is not None
                else None
            )

            speed = (
                speed_raw
                / 100.0
                if speed_raw is not None
                else None
            )

            heading = (
                course_raw
                / 10.0
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
                    fix_type=(
                        3
                        if values.get(
                            "GPS_numSat"
                        )
                        else None
                    ),
                    satellites=values.get(
                        "GPS_numSat"
                    ),
                    heading_deg=heading,
                    source_platform=self.platform_name,
                    raw={
                        **values,
                        "frame_type": "G",
                        "raw_offset": frame[
                            "raw_offset"
                        ],
                    },
                )
            )

        return records

    # ------------------------------------------------------------------
    # Navigation extraction
    # ------------------------------------------------------------------

    def extract_navigation(self):

        records = []

        for frame in self._iter_gps_frames():

            values = frame["values"]

            timestamp = (
                values.get(
                    "time",
                    0,
                )
                / 1_000_000.0
            )

            latitude_raw = values.get(
                "GPS_coord[0]"
            )

            longitude_raw = values.get(
                "GPS_coord[1]"
            )

            altitude_raw = values.get(
                "GPS_altitude"
            )

            latitude = (
                latitude_raw
                / 10_000_000.0
                if latitude_raw is not None
                else None
            )

            longitude = (
                longitude_raw
                / 10_000_000.0
                if longitude_raw is not None
                else None
            )

            altitude = (
                altitude_raw
                / 10.0
                if altitude_raw is not None
                else None
            )

            records.append(
                NavigationRecord(
                    timestamp=timestamp,
                    latitude=latitude,
                    longitude=longitude,
                    altitude_m=altitude,
                    source_platform=self.platform_name,
                    raw={
                        "dataset": "G",
                        **values,
                        "frame_type": "G",
                        "raw_offset": frame[
                            "raw_offset"
                        ],
                    },
                )
            )

        return records

    # ------------------------------------------------------------------
    # Battery helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_float(
        value,
        default=None,
    ):

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return default

    @staticmethod
    def _parse_current_meter(
        current_meter,
    ):

        if not current_meter:
            return 0.0, 0.0

        parts = [
            item.strip()
            for item in current_meter.split(",")
        ]

        if len(parts) < 2:
            return 0.0, 0.0

        offset = (
            BetaflightBlackboxParser
            ._safe_float(
                parts[0],
                0.0,
            )
        )

        scale = (
            BetaflightBlackboxParser
            ._safe_float(
                parts[1],
                0.0,
            )
        )

        return offset, scale

    @staticmethod
    def _convert_voltage(
        raw_value,
        headers,
    ):

        if raw_value is None:
            return None

        vbat_scale = (
            BetaflightBlackboxParser
            ._safe_float(
                headers.get(
                    "vbatscale"
                ),
                1.0,
            )
        )

        vbat_divider = (
            BetaflightBlackboxParser
            ._safe_float(
                headers.get(
                    "vbat_divider"
                ),
                10.0,
            )
        )

        vbat_multiplier = (
            BetaflightBlackboxParser
            ._safe_float(
                headers.get(
                    "vbat_multiplier"
                ),
                1.0,
            )
        )

        if vbat_divider == 0:
            return None

        if vbat_multiplier == 0:
            return None

        numerator = (
            raw_value
            * vbat_scale
            * 3300.0
            / 10.0
        )

        denominator = (
            4095.0
            * vbat_divider
        )

        voltage_centivolts = (
            numerator
            / denominator
            / vbat_multiplier
        )

        return (
            voltage_centivolts
            / 100.0
        )

    @staticmethod
    def _convert_current(
        raw_value,
        headers,
    ):

        if raw_value is None:
            return None

        offset, scale = (
            BetaflightBlackboxParser
            ._parse_current_meter(
                headers.get(
                    "currentMeter"
                )
            )
        )

        if scale == 0:
            return None

        millivolts = (
            raw_value
            * 33.0
            * 100.0
            / 4095.0
        )

        millivolts -= offset

        milliamps = (
            millivolts
            * 10000.0
            / scale
        )

        return (
            milliamps
            / 1000.0
        )

    # ------------------------------------------------------------------
    # Battery extraction
    # ------------------------------------------------------------------

    def extract_battery(self):

        raw = self._load_raw_header()

        headers = self._parse_headers(raw)

        records = []

        for frame in self._iter_main_frames():

            values = frame["values"]

            timestamp = (
                values.get(
                    "time",
                    0,
                )
                / 1_000_000.0
            )

            raw_voltage = values.get(
                "vbatLatest"
            )

            raw_current = values.get(
                "amperageLatest"
            )

            voltage_v = (
                self._convert_voltage(
                    raw_voltage,
                    headers,
                )
            )

            current_a = (
                self._convert_current(
                    raw_current,
                    headers,
                )
            )

            records.append(
                BatteryRecord(
                    timestamp=timestamp,
                    voltage_v=voltage_v,
                    current_a=current_a,
                    source_platform=self.platform_name,
                    raw={
                        **values,
                        "frame_type": "I",
                        "fields": values,
                        "raw_offset": frame[
                            "raw_offset"
                        ],
                        "blackbox_headers": {
                            "vbatref": headers.get(
                                "vbatref"
                            ),
                            "vbatscale": headers.get(
                                "vbatscale"
                            ),
                            "vbat_divider": headers.get(
                                "vbat_divider"
                            ),
                            "vbat_multiplier": headers.get(
                                "vbat_multiplier"
                            ),
                            "currentMeter": headers.get(
                                "currentMeter"
                            ),
                        },
                    },
                )
            )

        return records

    # ------------------------------------------------------------------
    # Normalized categories without a native Blackbox representation
    # ------------------------------------------------------------------

    def extract_telemetry(self):
        """
        Extract normalized telemetry records.

        Betaflight Blackbox data available to this parser does not currently
        expose a semantically equivalent MAVLink telemetry/link-status
        dataset. Do not synthesize telemetry records from unrelated fields.
        """
        return []

    def extract_failsafe(self):
        """
        Extract normalized failsafe records.

        No explicit failsafe dataset is currently decoded by this parser.
        Return an empty collection rather than inferring failsafe states from
        unrelated flight-controller fields.
        """
        return []

    def extract_commands(self):
        """
        Extract normalized command records.

        Betaflight Blackbox command/control messages are not currently
        decoded by this parser.
        """
        return []

    def extract_command_acks(self):
        """
        Extract normalized command acknowledgement records.

        No native COMMAND_ACK-equivalent Blackbox record is currently
        decoded by this parser.
        """
        return []

    def extract_states(self):
        """
        Extract normalized vehicle state records.

        State-bearing Blackbox fields are not currently decoded into the
        normalized state model.
        """
        return []

    def extract_parameters(self):
        """
        Extract normalized parameter records.

        Blackbox headers are preserved as metadata, but parameter-change
        records are not currently decoded.
        """
        return []

    def extract_events(self):
        """
        Extract normalized forensic events.

        P/S/E Blackbox frame decoding is not currently implemented, so no
        event records are synthesized.
        """
        return []

    def parse(self):
        """Build complete normalized evidence from the Betaflight log."""

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
