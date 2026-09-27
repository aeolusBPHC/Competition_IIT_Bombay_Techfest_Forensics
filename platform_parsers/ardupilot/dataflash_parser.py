from pathlib import Path
import struct

from platform_parsers.common.base_parser import BaseForensicParser
from platform_parsers.common.evidence_model import (
    EvidenceMetadata,
    GPSRecord,
    NavigationRecord,
    BatteryRecord,
    CommandRecord,
    CommandAckRecord,
    StateRecord,
    ParameterRecord,
    ForensicEvent,
    NormalizedEvidence,
)


class ArduPilotDataFlashParser(BaseForensicParser):

    platform_name = "ArduPilot"
    supported_formats = ["DataFlash", ".bin", ".log"]

    HEADER = b"\xA3\x95"
    HEADER_LEN = 3
    FMT_MESSAGE_ID = 128
    FMT_RECORD_LEN = 89

    FORMAT_TYPES = {
        "a": ("int16_array_32", 64),
        "b": ("int8", 1),
        "B": ("uint8", 1),
        "h": ("int16", 2),
        "H": ("uint16", 2),
        "i": ("int32", 4),
        "I": ("uint32", 4),
        "f": ("float", 4),
        "d": ("double", 8),
        "n": ("char4", 4),
        "N": ("char16", 16),
        "Z": ("char64", 64),
        "c": ("int16", 2),
        "C": ("uint16", 2),
        "e": ("int32", 4),
        "E": ("uint32", 4),
        "L": ("latlon", 4),
        "M": ("flight_mode", 1),
        "q": ("int64", 8),
        "Q": ("uint64", 8),
    }

    def __init__(self, evidence_path):
        super().__init__(evidence_path)
        self._data = None
        self._schemas = {}
        self._records = []

    # =========================================================
    # PLATFORM IDENTIFICATION
    # =========================================================

    @classmethod
    def identify(cls, evidence_path):

        path = Path(evidence_path)

        if not path.exists() or not path.is_file():

            return {
                "supported": False,
                "platform": cls.platform_name,
                "format": "DataFlash",
                "confidence": "NONE",
                "reason": "File does not exist",
            }

        if path.suffix.lower() not in {".bin", ".log"}:

            return {
                "supported": False,
                "platform": cls.platform_name,
                "format": "DataFlash",
                "confidence": "NONE",
                "reason": "Unsupported file extension",
            }

        try:

            data = path.read_bytes()

            if len(data) < cls.FMT_RECORD_LEN:

                raise ValueError("File too small")

            schemas = cls._scan_fmt_records(data)

            if not schemas:

                raise ValueError(
                    "No valid FMT records found"
                )

            return {
                "supported": True,
                "platform": cls.platform_name,
                "format": "DataFlash",
                "confidence": "HIGH",
                "reason": (
                    "Valid ArduPilot DataFlash "
                    "structure detected with "
                    f"{len(schemas)} FMT record(s)"
                ),
                "indicators": {
                    "packet_header": "A3 95",
                    "fmt_records": list(
                        schemas.values()
                    ),
                    "message_names": [
                        schema["name"]
                        for schema in schemas.values()
                    ],
                },
            }

        except Exception as exc:

            return {
                "supported": False,
                "platform": cls.platform_name,
                "format": "DataFlash",
                "confidence": "NONE",
                "reason": (
                    "DataFlash structure "
                    f"validation failed: {exc}"
                ),
            }

    # =========================================================
    # FMT SCHEMA RECOVERY
    # =========================================================

    @classmethod
    def _scan_fmt_records(cls, data):

        schemas = {}

        offset = 0

        while offset + cls.FMT_RECORD_LEN <= len(data):

            header = data.find(
                cls.HEADER,
                offset
            )

            if header < 0:
                break

            if (
                header + cls.FMT_RECORD_LEN
                > len(data)
            ):
                break

            msg_id = data[
                header + 2
            ]

            if msg_id != cls.FMT_MESSAGE_ID:

                offset = header + 2
                continue

            packet = data[
                header:
                header + cls.FMT_RECORD_LEN
            ]

            type_id = packet[3]
            msg_len = packet[4]

            name = (
                packet[5:9]
                .split(b"\x00", 1)[0]
                .decode(
                    "ascii",
                    errors="replace"
                )
            )

            fmt = (
                packet[9:25]
                .split(b"\x00", 1)[0]
                .decode(
                    "ascii",
                    errors="replace"
                )
            )

            labels = (
                packet[25:89]
                .split(b"\x00", 1)[0]
                .decode(
                    "ascii",
                    errors="replace"
                )
            )

            if (
                type_id == cls.FMT_MESSAGE_ID
                or not name
                or not fmt
            ):

                offset = header + 2
                continue

            if any(
                char not in cls.FORMAT_TYPES
                for char in fmt
            ):

                offset = header + 2
                continue

            schemas[type_id] = {
                "message_type": type_id,
                "message_length": msg_len,
                "name": name,
                "format": fmt,
                "labels": labels,
                "offset": header,
            }

            offset = (
                header +
                cls.FMT_RECORD_LEN
            )

        return schemas

    # =========================================================
    # LOAD DATA
    # =========================================================

    def _load(self):

        if self._data is None:

            self._data = (
                self.evidence_path.read_bytes()
            )

        if not self._schemas:

            self._schemas = (
                self._scan_fmt_records(
                    self._data
                )
            )

        return self._data

    # =========================================================
    # DATAFLASH FORMAT DECODER
    # =========================================================

    @classmethod
    def _decode_format(
        cls,
        payload,
        fmt,
        normalize=True,
    ):

        values = []

        offset = 0

        for code in fmt:

            if code not in cls.FORMAT_TYPES:

                raise ValueError(
                    "Unsupported DataFlash "
                    f"format character: {code}"
                )

            type_name, size = (
                cls.FORMAT_TYPES[code]
            )

            if (
                offset + size
                > len(payload)
            ):

                raise ValueError(
                    "Payload too short for "
                    f"format '{fmt}'"
                )

            chunk = payload[
                offset:
                offset + size
            ]

            # =================================================
            # INTEGER ARRAY
            # =================================================

            if code == "a":

                value = list(
                    struct.unpack(
                        "<32h",
                        chunk
                    )
                )

                values.append(value)

                offset += size

                continue

            # =================================================
            # BASIC INTEGER TYPES
            # =================================================

            elif code == "b":

                value = struct.unpack(
                    "<b",
                    chunk
                )[0]

            elif code == "B":

                value = struct.unpack(
                    "<B",
                    chunk
                )[0]

            elif code == "h":

                value = struct.unpack(
                    "<h",
                    chunk
                )[0]

            elif code == "H":

                value = struct.unpack(
                    "<H",
                    chunk
                )[0]

            elif code == "i":

                value = struct.unpack(
                    "<i",
                    chunk
                )[0]

            elif code == "I":

                value = struct.unpack(
                    "<I",
                    chunk
                )[0]

            # =================================================
            # FLOATING POINT
            # =================================================

            elif code == "f":

                value = struct.unpack(
                    "<f",
                    chunk
                )[0]

            elif code == "d":

                value = struct.unpack(
                    "<d",
                    chunk
                )[0]

            # =================================================
            # 64-BIT INTEGER
            # =================================================

            elif code == "q":

                value = struct.unpack(
                    "<q",
                    chunk
                )[0]

            elif code == "Q":

                value = struct.unpack(
                    "<Q",
                    chunk
                )[0]

            # =================================================
            # ARDUPILOT SPECIAL INTEGER TYPES
            # =================================================

            elif code == "c":

                raw_value = struct.unpack(
                    "<h",
                    chunk
                )[0]

                value = (
                    raw_value / 100.0
                    if normalize
                    else raw_value
                )

            elif code == "C":

                raw_value = struct.unpack(
                    "<H",
                    chunk
                )[0]

                value = (
                    raw_value / 100.0
                    if normalize
                    else raw_value
                )

            elif code == "e":

                raw_value = struct.unpack(
                    "<i",
                    chunk
                )[0]

                value = (
                    raw_value / 100.0
                    if normalize
                    else raw_value
                )

            elif code == "E":

                raw_value = struct.unpack(
                    "<I",
                    chunk
                )[0]

                value = (
                    raw_value / 100.0
                    if normalize
                    else raw_value
                )

            elif code == "L":

                raw_value = struct.unpack(
                    "<i",
                    chunk
                )[0]

                value = (
                    raw_value / 1e7
                    if normalize
                    else raw_value
                )

            elif code == "M":

                value = struct.unpack(
                    "<B",
                    chunk
                )[0]

            # =================================================
            # STRING / CHARACTER ARRAYS
            # =================================================

            elif code in {
                "n",
                "N",
                "Z",
            }:

                value = (
                    chunk
                    .split(
                        b"\x00",
                        1
                    )[0]
                    .decode(
                        "ascii",
                        errors="replace"
                    )
                )

            # =================================================
            # UNKNOWN
            # =================================================

            else:

                raise ValueError(
                    f"Unhandled format code: {code}"
                )

            values.append(value)

            offset += size

        return values

    # =========================================================
    # RECORD ITERATOR
    # =========================================================

    def _iter_records(self):

        data = self._load()

        offset = 0

        while (
            offset + self.HEADER_LEN
            <= len(data)
        ):

            # -------------------------------------------------
            # Find next packet header
            # -------------------------------------------------

            header = data.find(
                self.HEADER,
                offset
            )

            if header < 0:
                break

            # -------------------------------------------------
            # Header complete?
            # -------------------------------------------------

            if (
                header + self.HEADER_LEN
                > len(data)
            ):

                break

            # -------------------------------------------------
            # Message ID
            # -------------------------------------------------

            msg_id = data[
                header + 2
            ]

            # -------------------------------------------------
            # Find schema
            # -------------------------------------------------

            schema = self._schemas.get(
                msg_id
            )

            if schema is None:

                offset = header + 2
                continue

            # -------------------------------------------------
            # Message length
            # -------------------------------------------------

            msg_len = schema[
                "message_length"
            ]

            if msg_len < self.HEADER_LEN:

                offset = header + 2
                continue

            # -------------------------------------------------
            # Packet end
            # -------------------------------------------------

            end = (
                header +
                msg_len
            )

            if end > len(data):

                break

            packet = data[
                header:end
            ]

            # -------------------------------------------------
            # Remove 3-byte DataFlash header
            # -------------------------------------------------

            payload = packet[3:]

            expected_payload_len = (
                msg_len - 3
            )

            if (
                len(payload)
                != expected_payload_len
            ):

                offset = header + 2
                continue

            # =================================================
            # DECODE
            # =================================================

            try:

                values = (
                    self._decode_format(
                        payload,
                        schema["format"],
                        normalize=True,
                    )
                )

                raw_values = (
                    self._decode_format(
                        payload,
                        schema["format"],
                        normalize=False,
                    )
                )

                labels = [
                    label.strip()
                    for label in
                    schema["labels"].split(",")
                ]

                # -------------------------------------------------
                # Forensic validation
                # -------------------------------------------------

                if len(labels) != len(values):

                    raise ValueError(
                        "FMT schema mismatch: "
                        f"{schema['name']} has "
                        f"{len(values)} decoded values "
                        f"but {len(labels)} labels"
                    )

                if (
                    len(raw_values)
                    != len(values)
                ):

                    raise ValueError(
                        "Raw/normalized value "
                        "count mismatch: "
                        f"{schema['name']} has "
                        f"{len(raw_values)} raw values "
                        f"and {len(values)} normalized values"
                    )

                record = {

                    "message_type": msg_id,

                    "name": schema["name"],

                    "format": schema["format"],

                    "labels": labels,

                    # Normalized physical values
                    "values": values,

                    # Original decoded DataFlash values
                    "raw_values": raw_values,

                    # Original binary packet
                    "raw": packet,

                    "offset": header,
                }

                yield record

                # -------------------------------------------------
                # Move to next packet
                # -------------------------------------------------

                offset = end

            except Exception as exc:

                print(
                    "DECODE ERROR: "
                    f"message={schema['name']} "
                    f"type={msg_id} "
                    f"offset={header} "
                    f"error={exc}"
                )

                offset = header + 2

    # =========================================================
    # METADATA
    # =========================================================

    def get_metadata(self):

        self._load()

        return EvidenceMetadata(

            source_file=str(
                self.evidence_path
            ),

            platform=self.platform_name,

            format="DataFlash",

            metadata={

                "schema_count": len(
                    self._schemas
                ),

                "message_types": [
                    schema["name"]
                    for schema
                    in self._schemas.values()
                ],
            },
        )

    # =========================================================
    # GPS
    # =========================================================

    def extract_gps(self):

        gps_records = []

        for record in self._iter_records():

            if record["name"] not in {
                "GPS",
                "GPS2",
            }:

                continue

            values = record["values"]

            raw_values = record[
                "raw_values"
            ]

            labels = record["labels"]

            fields = dict(
                zip(
                    labels,
                    values
                )
            )

            raw_fields = dict(
                zip(
                    labels,
                    raw_values
                )
            )

            # -------------------------------------------------
            # Timestamp
            # -------------------------------------------------

            timestamp = fields.get(
                "TimeUS"
            )

            # -------------------------------------------------
            # Latitude
            # -------------------------------------------------

            latitude = fields.get(
                "Lat"
            )

            # -------------------------------------------------
            # Longitude
            # -------------------------------------------------

            longitude = fields.get(
                "Lng"
            )

            if longitude is None:

                longitude = fields.get(
                    "Lon"
                )

            # -------------------------------------------------
            # Altitude
            # -------------------------------------------------

            altitude = fields.get(
                "Alt"
            )

            if altitude is None:

                altitude = fields.get(
                    "RAlt"
                )

            # -------------------------------------------------
            # Other GPS fields
            # -------------------------------------------------

            speed = fields.get(
                "Spd"
            )

            satellites = fields.get(
                "NSats"
            )

            hdop = fields.get(
                "HDop"
            )

            # -------------------------------------------------
            # TimeUS is microseconds
            # -------------------------------------------------

            if timestamp is not None:

                timestamp = (
                    timestamp /
                    1_000_000.0
                )

            gps_records.append(

                GPSRecord(

                    timestamp=timestamp,

                    latitude=latitude,

                    longitude=longitude,

                    altitude_m=altitude,

                    speed_m_s=speed,

                    satellites=satellites,

                    hdop=hdop,

                    source_platform=(
                        self.platform_name
                    ),

                    raw=raw_fields,
                )
            )

        return gps_records
 
    # =========================================================
    # NAVIGATION
    # =========================================================

    def extract_navigation(self):

        navigation_records = []

        for record in self._iter_records():

            if record["name"] != "POS":

                continue

            values = record["values"]

            raw_values = record[
                "raw_values"
            ]

            labels = record["labels"]

            fields = dict(
                zip(
                    labels,
                    values
                )
            )

            raw_fields = dict(
                zip(
                    labels,
                    raw_values
                )
            )

            # -------------------------------------------------
            # Timestamp
            # -------------------------------------------------

            timestamp = fields.get(
                "TimeUS"
            )

            if timestamp is None:

                continue

            timestamp = (
                timestamp /
                1_000_000.0
            )

            # -------------------------------------------------
            # Position
            # -------------------------------------------------

            latitude = fields.get(
                "Lat"
            )

            longitude = fields.get(
                "Lng"
            )

            if longitude is None:

                longitude = fields.get(
                    "Lon"
                )

            altitude = fields.get(
                "Alt"
            )

            # -------------------------------------------------
            # Relative altitude
            # -------------------------------------------------

            relative_home_altitude = fields.get(
                "RelHomeAlt"
            )

            # -------------------------------------------------
            # Create normalized navigation record
            # -------------------------------------------------

            navigation_records.append(
                NavigationRecord(

                    timestamp=timestamp,

                    latitude=latitude,

                    longitude=longitude,

                    altitude_m=altitude,

                    delta_altitude_m=(
                        relative_home_altitude
                    ),

                    source_platform=(
                        self.platform_name
                    ),

                    raw={
                        "dataset": "POS",

                        "timestamp_raw": (
                            raw_fields.get(
                                "TimeUS"
                            )
                        ),

                        "latitude_raw": (
                            raw_fields.get(
                                "Lat"
                            )
                        ),

                        "longitude_raw": (
                            raw_fields.get(
                                "Lng"
                            )
                        ),

                        "altitude_raw": (
                            raw_fields.get(
                                "Alt"
                            )
                        ),

                        "relative_home_altitude": (
                            relative_home_altitude
                        ),

                        "relative_origin_altitude": (
                            fields.get(
                                "RelOriginAlt"
                            )
                        ),

                        "raw_fields": raw_fields,
                    },
                )
            )

        return navigation_records

    # =========================================================
    # BATTERY
    # =========================================================

    def extract_battery(self):
        """
        Extract battery-related DataFlash records into
        normalized BatteryRecord objects.

        ArduPilot battery logging can vary between firmware
        versions and battery-monitor implementations.

        Therefore this method does not assume one fixed BAT
        schema. It identifies records whose fields contain
        battery-related measurements and maps only fields that
        are actually present.
        """

        records = []

        battery_names = {
            "BAT",
            "BAT2",
            "BAT3",
            "BAT4",
        }

        for record in self._iter_records():

            if record["name"] not in battery_names:
                continue

            labels = record["labels"]
            values = record["values"]
            raw_values = record["raw_values"]

            fields = dict(
                zip(
                    labels,
                    values,
                )
            )

            raw_fields = dict(
                zip(
                    labels,
                    raw_values,
                )
            )

            timestamp_raw = fields.get(
                "TimeUS"
            )

            if timestamp_raw is None:
                continue

            voltage = fields.get("Volt")

            if voltage is None:
                voltage = fields.get("Volt2")

            current = fields.get("Curr")

            if current is None:
                current = fields.get("Curr1")

            current_average = fields.get(
                "CurrAvg"
            )

            if current_average is None:
                current_average = fields.get(
                    "Curr_Avg"
                )

            discharged = fields.get(
                "CurrTot"
            )

            if discharged is None:
                discharged = fields.get(
                    "Consumed"
                )

            remaining = fields.get(
                "RemPct"
            )

            temperature = fields.get(
                "Temp"
            )

            records.append(
                BatteryRecord(

                    timestamp=(
                        timestamp_raw
                        / 1_000_000.0
                    ),

                    voltage_v=voltage,

                    current_a=current,

                    current_average_a=(
                        current_average
                    ),

                    discharged_mah=(
                        discharged
                    ),

                    remaining=(
                        remaining / 100.0
                        if remaining is not None
                        and remaining > 1
                        else remaining
                    ),

                    temperature_c=temperature,

                    source_platform=(
                        self.platform_name
                    ),

                    raw={
                        "dataset": record["name"],
                        "message_type": record[
                            "message_type"
                        ],
                        "format": record[
                            "format"
                        ],
                        "labels": labels,
                        "fields": fields,
                        "raw_fields": raw_fields,
                        "timestamp_raw": (
                            timestamp_raw
                        ),
                    },
                )
            )

        return records

    # =========================================================
    # TELEMETRY
    # =========================================================

    def extract_telemetry(self):
        """
        DataFlash telemetry extraction is not enabled yet.

        The current normalized DataFlash evidence does not contain
        a native telemetry dataset with semantics that can be mapped
        defensibly to TelemetryRecord.

        Do not synthesize telemetry records from unrelated DataFlash
        records.
        """

        return []

    # =========================================================
    # FAILSAFE
    # =========================================================

    def extract_failsafe(self):
        """
        DataFlash failsafe extraction is not enabled yet.

        The current normalized DataFlash evidence does not contain
        a dedicated native failsafe dataset.

        ERR and MSG records are preserved as forensic events and
        are not reclassified as failsafe records without explicit
        evidence.

        Do not synthesize failsafe records.
        """

        return []

    # =========================================================
    # COMMANDS
    # =========================================================

    def extract_commands(self):

        commands = []

        for record in self._iter_records():

            if record["name"] != "MAVC":

                continue

            fields = dict(
                zip(
                    record["labels"],
                    record["values"]
                )
            )

            raw_fields = dict(
                zip(
                    record["labels"],
                    record["raw_values"]
                )
            )

            commands.append(

                CommandRecord(

                    timestamp=self._timestamp(
                        fields
                    ),

                    command_id=fields.get(
                        "Cmd"
                    ),

                    source_system=fields.get(
                        "SS"
                    ),

                    source_component=fields.get(
                        "SC"
                    ),

                    target_system=fields.get(
                        "TS"
                    ),

                    target_component=fields.get(
                        "TC"
                    ),

                    parameters={
                        key: value
                        for key, value
                        in fields.items()
                        if key.startswith("P")
                    },

                    source_platform=(
                        self.platform_name
                    ),

                    raw=raw_fields,
                )
            )

        return commands

    # =========================================================
    # STATES
    # =========================================================

    def extract_states(self):

        states = []

        for record in self._iter_records():

            if record["name"] not in {
                "MODE",
                "ARM",
            }:

                continue

            fields = dict(
                zip(
                    record["labels"],
                    record["values"]
                )
            )

            raw_fields = dict(
                zip(
                    record["labels"],
                    record["raw_values"]
                )
            )

            timestamp = self._timestamp(
                fields
            )

            # -------------------------------------------------
            # Flight mode
            # -------------------------------------------------

            flight_mode = fields.get(
                "Mode"
            )

            if flight_mode is None:

                flight_mode = fields.get(
                    "ModeNum"
                )

            # -------------------------------------------------
            # Armed state
            # -------------------------------------------------

            armed = None

            if record["name"] == "ARM":

                armed = fields.get(
                    "ArmState"
                )

            states.append(

                StateRecord(

                    timestamp=timestamp,

                    armed=armed,

                    flight_mode=flight_mode,

                    source_platform=(
                        self.platform_name
                    ),

                    raw=raw_fields,
                )
            )

        return states

    # =========================================================
    # PARAMETERS
    # =========================================================

    def extract_parameters(self):

        parameters = []

        for record in self._iter_records():

            if record["name"] != "PARM":

                continue

            fields = dict(
                zip(
                    record["labels"],
                    record["values"]
                )
            )

            raw_fields = dict(
                zip(
                    record["labels"],
                    record["raw_values"]
                )
            )

            timestamp = self._timestamp(
                fields
            )

            name = fields.get(
                "Name"
            )

            value = fields.get(
                "Value"
            )

            if name is None:

                continue

            parameters.append(

                ParameterRecord(

                    timestamp=timestamp,

                    name=str(name),

                    value=value,

                    source_platform=(
                        self.platform_name
                    ),

                    raw=raw_fields,
                )
            )

        return parameters

    # =========================================================
    # EVENTS
    # =========================================================

    def extract_events(self):

        events = []

        for record in self._iter_records():

            if record["name"] not in {
                "EV",
                "ERR",
                "MSG",
            }:

                continue

            fields = dict(
                zip(
                    record["labels"],
                    record["values"]
                )
            )

            raw_fields = dict(
                zip(
                    record["labels"],
                    record["raw_values"]
                )
            )

            timestamp = self._timestamp(
                fields
            )

            # -------------------------------------------------
            # EV
            # -------------------------------------------------

            if record["name"] == "EV":

                description = (
                    "ArduPilot event "
                    f"ID {fields.get('Id')}"
                )

            # -------------------------------------------------
            # ERR
            # -------------------------------------------------

            elif record["name"] == "ERR":

                description = (
                    "ArduPilot error "
                    f"subsystem="
                    f"{fields.get('Subsys')} "
                    f"code="
                    f"{fields.get('ECode')}"
                )

            # -------------------------------------------------
            # MSG
            # -------------------------------------------------

            else:

                description = fields.get(
                    "Message"
                )

            events.append(

                ForensicEvent(

                    timestamp=timestamp,

                    event_type=record["name"],

                    description=description,

                    source_platform=(
                        self.platform_name
                    ),

                    raw=raw_fields,
                )
            )

        return events

    # =========================================================
    # COMMAND ACKS
    # =========================================================

    def extract_command_acks(self):

        # DataFlash MAVC records provide
        # logged command-related information.
        #
        # A separate generic COMMAND_ACK
        # DataFlash record is not guaranteed.
        #
        # Therefore we do not synthesize
        # acknowledgement records.

        return []

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _timestamp(fields):

        timestamp = fields.get(
            "TimeUS"
        )

        if timestamp is None:

            return None

        return (
            timestamp /
            1_000_000.0
        )

    # =========================================================
    # PARSE
    # =========================================================

    def parse(self):

        self._load()

        metadata = self.get_metadata()

        return NormalizedEvidence(
            metadata=metadata,

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
