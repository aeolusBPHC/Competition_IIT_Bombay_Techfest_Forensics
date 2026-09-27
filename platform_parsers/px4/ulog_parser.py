from pathlib import Path
from typing import Any

from pyulog import ULog

from platform_parsers.common.base_parser import BaseForensicParser

from platform_parsers.common.evidence_model import (
    EvidenceMetadata,
    GPSRecord,
    NavigationRecord,
    TrajectoryRecord,
    BatteryRecord,
    TelemetryRecord,
    FailsafeRecord,
    CommandRecord,
    CommandAckRecord,
    StateRecord,
    ParameterRecord,
    ForensicEvent,
)


class PX4ULogParser(BaseForensicParser):
    """
    Independent PX4 ULog forensic parser.

    This parser belongs to the new multi-platform architecture
    and does NOT replace the original PX4 parser.
    """

    platform_name = "PX4"

    supported_formats = [
        "ULog",
        ".ulg",
    ]

    def __init__(self, evidence_path):
        super().__init__(evidence_path)

        self.ulog = ULog(str(self.evidence_path))

    # ---------------------------------------------------------
    # IDENTIFICATION
    # ---------------------------------------------------------

    @classmethod
    def identify(cls, evidence_path):
        """
        Determine whether the supplied file appears to be
        a PX4 ULog artifact.
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
                "reason": "Path is not a file",
            }

        if path.suffix.lower() == ".ulg":
            return {
                "supported": True,
                "platform": cls.platform_name,
                "format": "ULog",
                "confidence": "HIGH",
                "reason": "ULog file extension detected",
            }

        return {
            "supported": False,
            "platform": cls.platform_name,
            "format": None,
            "confidence": "NONE",
            "reason": "File extension is not .ulg",
        }

    # ---------------------------------------------------------
    # INTERNAL DATASET HELPERS
    # ---------------------------------------------------------

    def _dataset(self, name):
        """
        Return the first PX4 ULog dataset with the supplied name.
        """

        for dataset in self.ulog.data_list:
            if dataset.name == name:
                return dataset

        return None

    def _datasets(self, name):
        """
        Return all PX4 ULog datasets with the supplied name.

        This is important for topics such as telemetry_status,
        which may occur as multiple instances in a ULog.
        """

        return [
            dataset
            for dataset in self.ulog.data_list
            if dataset.name == name
        ]

    @staticmethod
    def _value(data, field, index):
        """
        Safely extract a value from pyulog dataset.data.

        pyulog exposes dataset.data as a dictionary of arrays.
        """

        if data is None:
            return None

        if field not in data:
            return None

        try:
            value = data[field][index]

            if hasattr(value, "item"):
                return value.item()

            return value

        except (IndexError, KeyError):
            return None

    @staticmethod
    def _bool_value(data, field, index):
        """
        Safely extract a field and convert it to bool.
        """

        value = PX4ULogParser._value(data, field, index)

        if value is None:
            return None

        return bool(value)

    @staticmethod
    def _dataset_instance(dataset):
        """
        Return pyulog's multi_id for a dataset when available.

        Multiple instances of the same PX4 topic must not be
        silently merged.
        """

        multi_id = getattr(dataset, "multi_id", None)

        if multi_id is None:
            return 0

        try:
            return int(multi_id)
        except (TypeError, ValueError):
            return 0

    # ---------------------------------------------------------
    # METADATA
    # ---------------------------------------------------------

    def get_metadata(self):
        """
        Extract basic ULog metadata.
        """

        start_time = None
        end_time = None
        duration = None

        if self.ulog.start_timestamp is not None:
            start_time = self.ulog.start_timestamp / 1_000_000.0

        if self.ulog.last_timestamp is not None:
            end_time = self.ulog.last_timestamp / 1_000_000.0

        if (
            self.ulog.start_timestamp is not None
            and self.ulog.last_timestamp is not None
        ):
            duration = (
                self.ulog.last_timestamp
                - self.ulog.start_timestamp
            ) / 1_000_000.0

        metadata = dict(self.ulog.msg_info_dict)

        return EvidenceMetadata(
            source_file=str(self.evidence_path),
            platform=self.platform_name,
            format="ULog",
            firmware=metadata.get("ver_sw"),
            firmware_version=metadata.get("ver_sw"),
            vehicle_type=metadata.get("sys_name"),
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            metadata=metadata,
        )

    # ---------------------------------------------------------
    # GPS
    # ---------------------------------------------------------

    def extract_gps(self):
        """
        Extract vehicle_gps_position into normalized GPSRecord objects.
        """

        dataset = self._dataset("vehicle_gps_position")

        if dataset is None:
            return []

        data = dataset.data
        timestamps = data.get("timestamp", [])

        records = []

        for i in range(len(timestamps)):

            timestamp = self._value(
                data,
                "timestamp",
                i,
            )

            if timestamp is None:
                continue

            records.append(
                GPSRecord(
                    timestamp=timestamp / 1_000_000.0,

                    latitude=self._value(
                        data,
                        "latitude_deg",
                        i,
                    ),

                    longitude=self._value(
                        data,
                        "longitude_deg",
                        i,
                    ),

                    altitude_m=self._value(
                        data,
                        "altitude_msl_m",
                        i,
                    ),

                    speed_m_s=self._value(
                        data,
                        "vel_m_s",
                        i,
                    ),

                    fix_type=self._value(
                        data,
                        "fix_type",
                        i,
                    ),

                    satellites=self._value(
                        data,
                        "satellites_used",
                        i,
                    ),

                    hdop=self._value(
                        data,
                        "hdop",
                        i,
                    ),

                    vdop=self._value(
                        data,
                        "vdop",
                        i,
                    ),

                    heading_deg=self._value(
                        data,
                        "heading",
                        i,
                    ),

                    jamming_state=self._value(
                        data,
                        "jamming_state",
                        i,
                    ),

                    spoofing_state=self._value(
                        data,
                        "spoofing_state",
                        i,
                    ),

                    source_platform=self.platform_name,
                )
            )

        return records

    # ---------------------------------------------------------
    # NAVIGATION
    # ---------------------------------------------------------

    def extract_navigation(self):
        """
        Extract vehicle_global_position into normalized
        NavigationRecord objects.
        """

        dataset = self._dataset("vehicle_global_position")

        if dataset is None:
            return []

        data = dataset.data
        timestamps = data.get("timestamp", [])

        records = []

        for i in range(len(timestamps)):

            timestamp = self._value(
                data,
                "timestamp",
                i,
            )

            if timestamp is None:
                continue

            raw = {
                "dataset": "vehicle_global_position",
                "instance": self._dataset_instance(dataset),
                "timestamp_sample": self._value(
                    data,
                    "timestamp_sample",
                    i,
                ),
            }

            records.append(
                NavigationRecord(
                    timestamp=timestamp / 1_000_000.0,

                    latitude=self._value(
                        data,
                        "lat",
                        i,
                    ),

                    longitude=self._value(
                        data,
                        "lon",
                        i,
                    ),

                    altitude_m=self._value(
                        data,
                        "alt",
                        i,
                    ),

                    altitude_ellipsoid_m=self._value(
                        data,
                        "alt_ellipsoid",
                        i,
                    ),

                    delta_altitude_m=self._value(
                        data,
                        "delta_alt",
                        i,
                    ),

                    delta_terrain_m=self._value(
                        data,
                        "delta_terrain",
                        i,
                    ),

                    horizontal_position_accuracy_m=self._value(
                        data,
                        "eph",
                        i,
                    ),

                    vertical_position_accuracy_m=self._value(
                        data,
                        "epv",
                        i,
                    ),

                    latitude_longitude_valid=self._bool_value(
                        data,
                        "lat_lon_valid",
                        i,
                    ),

                    altitude_valid=self._bool_value(
                        data,
                        "alt_valid",
                        i,
                    ),

                    terrain_altitude_valid=self._bool_value(
                        data,
                        "terrain_alt_valid",
                        i,
                    ),

                    latitude_longitude_reset_counter=self._value(
                        data,
                        "lat_lon_reset_counter",
                        i,
                    ),

                    altitude_reset_counter=self._value(
                        data,
                        "alt_reset_counter",
                        i,
                    ),

                    terrain_reset_counter=self._value(
                        data,
                        "terrain_alt_reset_counter",
                        i,
                    ),

                    dead_reckoning=self._bool_value(
                        data,
                        "dead_reckoning",
                        i,
                    ),

                    source_platform=self.platform_name,

                    raw=raw,
                )
            )

        return records
       
    # ---------------------------------------------------------------
    # Battery extraction
    # ---------------------------------------------------------------

    def extract_trajectory(self):
        """
        Extract PX4's native local-position estimator state.

        Primary source:
            vehicle_local_position

        This is deliberately separate from extract_navigation(), which
        continues to represent vehicle_global_position. The normalized
        trajectory layer therefore does not have to know PX4 topic names.

        Ground-truth topics are intentionally excluded: they are useful
        for validation of simulation data, but must not become normal
        model input.
        """

        dataset = self._dataset(
            "vehicle_local_position"
        )

        if dataset is None:
            return []

        data = dataset.data

        timestamps = data.get("timestamp", [])

        if len(timestamps) == 0:
            return []

        records = []

        for i in range(len(timestamps)):

            timestamp = self._value(
                data,
                "timestamp_sample",
                i,
            )

            if timestamp is None:
                timestamp = self._value(
                    data,
                    "timestamp",
                    i,
                )

            if timestamp is None:
                continue

            timestamp = (
                float(timestamp)
                / 1_000_000.0
            )

            x = self._value(data, "x", i)
            y = self._value(data, "y", i)
            z = self._value(data, "z", i)

            vx = self._value(data, "vx", i)
            vy = self._value(data, "vy", i)
            vz = self._value(data, "vz", i)

            ax = self._value(data, "ax", i)
            ay = self._value(data, "ay", i)
            az = self._value(data, "az", i)

            xy_valid = self._bool_value(
                data,
                "xy_valid",
                i,
            )

            z_valid = self._bool_value(
                data,
                "z_valid",
                i,
            )

            vxy_valid = self._bool_value(
                data,
                "v_xy_valid",
                i,
            )

            vz_valid = self._bool_value(
                data,
                "v_z_valid",
                i,
            )

            # Acceleration has no universal PX4 validity flag in this
            # topic. Treat finite values as available, but preserve that
            # this is an estimator-provided acceleration.
            acceleration_values = (
                ax,
                ay,
                az,
            )

            acceleration_valid = all(
                value is not None
                for value in acceleration_values
            )

            position_valid = bool(
                xy_valid
                and z_valid
            )

            velocity_valid = bool(
                vxy_valid
                and vz_valid
            )

            raw = {
                "dataset": "vehicle_local_position",
                "instance": self._dataset_instance(dataset),

                "timestamp": self._value(
                    data,
                    "timestamp",
                    i,
                ),

                "timestamp_sample": self._value(
                    data,
                    "timestamp_sample",
                    i,
                ),

                "x": x,
                "y": y,
                "z": z,

                "vx": vx,
                "vy": vy,
                "vz": vz,

                "ax": ax,
                "ay": ay,
                "az": az,

                "xy_valid": xy_valid,
                "z_valid": z_valid,

                "v_xy_valid": vxy_valid,
                "v_z_valid": vz_valid,

                "xy_reset_counter": self._value(
                    data,
                    "xy_reset_counter",
                    i,
                ),

                "z_reset_counter": self._value(
                    data,
                    "z_reset_counter",
                    i,
                ),

                "vxy_reset_counter": self._value(
                    data,
                    "vxy_reset_counter",
                    i,
                ),

                "vz_reset_counter": self._value(
                    data,
                    "vz_reset_counter",
                    i,
                ),

                "xy_global": self._value(
                    data,
                    "xy_global",
                    i,
                ),

                "z_global": self._value(
                    data,
                    "z_global",
                    i,
                ),
            }

            records.append(
                TrajectoryRecord(
                    timestamp=timestamp,

                    x_m=x,
                    y_m=y,
                    z_m=z,

                    vx_m_s=vx,
                    vy_m_s=vy,
                    vz_m_s=vz,

                    ax_m_s2=ax,
                    ay_m_s2=ay,
                    az_m_s2=az,

                    position_valid=position_valid,
                    horizontal_position_valid=bool(
                        xy_valid
                    ),
                    vertical_position_valid=bool(
                        z_valid
                    ),

                    velocity_valid=velocity_valid,
                    horizontal_velocity_valid=bool(
                        vxy_valid
                    ),
                    vertical_velocity_valid=bool(
                        vz_valid
                    ),

                    acceleration_valid=acceleration_valid,

                    position_source="native",
                    velocity_source="native",
                    acceleration_source=(
                        "native"
                        if acceleration_valid
                        else "unavailable"
                    ),

                    position_reset_counter=self._value(
                        data,
                        "xy_reset_counter",
                        i,
                    ),

                    vertical_reset_counter=self._value(
                        data,
                        "z_reset_counter",
                        i,
                    ),

                    velocity_reset_counter=self._value(
                        data,
                        "vxy_reset_counter",
                        i,
                    ),

                    vertical_velocity_reset_counter=(
                        self._value(
                            data,
                            "vz_reset_counter",
                            i,
                        )
                    ),

                    source_platform=self.platform_name,

                    raw=raw,
                )
            )

        return records

    def extract_battery(self):

        dataset = self._dataset("battery_status")

        if dataset is None:
            return []

        data = dataset.data

        timestamps = data.get("timestamp", [])

        records = []

        for i in range(len(timestamps)):

            timestamp = self._value(
                data,
                "timestamp",
                i,
            )

            if timestamp is None:
                continue

            cell_voltages = []

            for cell_index in range(14):

                value = self._value(
                    data,
                    f"voltage_cell_v[{cell_index}]",
                    i,
                )

                if value is not None:
                    cell_voltages.append(
                        float(value)
                    )

            records.append(
                BatteryRecord(

                    timestamp=(
                        timestamp
                        / 1_000_000.0
                    ),

                    voltage_v=self._value(
                        data,
                        "voltage_v",
                        i,
                    ),

                    current_a=self._value(
                        data,
                        "current_a",
                        i,
                    ),

                    current_average_a=self._value(
                        data,
                        "current_average_a",
                        i,
                    ),

                    discharged_mah=self._value(
                        data,
                        "discharged_mah",
                        i,
                    ),

                    remaining=self._value(
                        data,
                        "remaining",
                        i,
                    ),

                    time_remaining_s=self._value(
                        data,
                        "time_remaining_s",
                        i,
                    ),

                    temperature_c=self._value(
                        data,
                        "temperature",
                        i,
                    ),

                    cell_count=self._value(
                        data,
                        "cell_count",
                        i,
                    ),

                    cell_voltages_v=cell_voltages,

                    max_cell_voltage_delta_v=(
                        self._value(
                            data,
                            "max_cell_voltage_delta",
                            i,
                        )
                    ),

                    capacity_mah=self._value(
                        data,
                        "capacity",
                        i,
                    ),

                    cycle_count=self._value(
                        data,
                        "cycle_count",
                        i,
                    ),

                    state_of_health=self._value(
                        data,
                        "state_of_health",
                        i,
                    ),

                    connected=self._bool_value(
                        data,
                        "connected",
                        i,
                    ),

                    faults=self._value(
                        data,
                        "faults",
                        i,
                    ),

                    warning=self._value(
                        data,
                        "warning",
                        i,
                    ),

                    source_platform=self.platform_name,

                    raw={
                        "dataset": "battery_status",

                        "timestamp": timestamp,

                        "voltage_v": self._value(
                            data,
                            "voltage_v",
                            i,
                        ),

                        "current_a": self._value(
                            data,
                            "current_a",
                            i,
                        ),

                        "current_average_a": (
                            self._value(
                                data,
                                "current_average_a",
                                i,
                            )
                        ),

                        "discharged_mah": (
                            self._value(
                                data,
                                "discharged_mah",
                                i,
                            )
                        ),

                        "remaining": self._value(
                            data,
                            "remaining",
                            i,
                        ),

                        "time_remaining_s": (
                            self._value(
                                data,
                                "time_remaining_s",
                                i,
                            )
                        ),

                        "temperature": self._value(
                            data,
                            "temperature",
                            i,
                        ),

                        "cell_count": self._value(
                            data,
                            "cell_count",
                            i,
                        ),

                        "cell_voltages_v": (
                            cell_voltages.copy()
                        ),

                        "max_cell_voltage_delta": (
                            self._value(
                                data,
                                "max_cell_voltage_delta",
                                i,
                            )
                        ),

                        "capacity": self._value(
                            data,
                            "capacity",
                            i,
                        ),

                        "cycle_count": self._value(
                            data,
                            "cycle_count",
                            i,
                        ),

                        "state_of_health": (
                            self._value(
                                data,
                                "state_of_health",
                                i,
                            )
                        ),

                        "connected": self._value(
                            data,
                            "connected",
                            i,
                        ),

                        "faults": self._value(
                            data,
                            "faults",
                            i,
                        ),

                        "warning": self._value(
                            data,
                            "warning",
                            i,
                        ),

                        "source": self._value(
                            data,
                            "source",
                            i,
                        ),

                        "priority": self._value(
                            data,
                            "priority",
                            i,
                        ),

                        "id": self._value(
                            data,
                            "id",
                            i,
                        ),

                        "is_powering_off": (
                            self._value(
                                data,
                                "is_powering_off",
                                i,
                            )
                        ),

                        "is_required": (
                            self._value(
                                data,
                                "is_required",
                                i,
                            )
                        ),
                    },
                )
            )

        return records

    # ---------------------------------------------------------
    # TELEMETRY
    # ---------------------------------------------------------

    def extract_telemetry(self):
        """
        Extract all telemetry_status instances into normalized
        TelemetryRecord objects.

        Multiple telemetry_status instances are preserved through
        the raw dataset instance field.
        """

        datasets = self._datasets("telemetry_status")

        records = []

        for dataset in datasets:

            data = dataset.data
            timestamps = data.get("timestamp", [])

            instance = self._dataset_instance(dataset)

            for i in range(len(timestamps)):

                timestamp = self._value(
                    data,
                    "timestamp",
                    i,
                )

                if timestamp is None:
                    continue

                raw = {
                    "dataset": "telemetry_status",
                    "instance": instance,
                }

                records.append(
                    TelemetryRecord(
                        timestamp=timestamp / 1_000_000.0,

                        data_rate=self._value(
                            data,
                            "data_rate",
                            i,
                        ),

                        rate_multiplier=self._value(
                            data,
                            "rate_multiplier",
                            i,
                        ),

                        tx_rate_avg=self._value(
                            data,
                            "tx_rate_avg",
                            i,
                        ),

                        tx_error_rate_avg=self._value(
                            data,
                            "tx_error_rate_avg",
                            i,
                        ),

                        tx_message_count=self._value(
                            data,
                            "tx_message_count",
                            i,
                        ),

                        tx_buffer_overruns=self._value(
                            data,
                            "tx_buffer_overruns",
                            i,
                        ),

                        rx_rate_avg=self._value(
                            data,
                            "rx_rate_avg",
                            i,
                        ),

                        rx_message_count=self._value(
                            data,
                            "rx_message_count",
                            i,
                        ),

                        rx_message_lost_count=self._value(
                            data,
                            "rx_message_lost_count",
                            i,
                        ),

                        rx_buffer_overruns=self._value(
                            data,
                            "rx_buffer_overruns",
                            i,
                        ),

                        rx_parse_errors=self._value(
                            data,
                            "rx_parse_errors",
                            i,
                        ),

                        rx_packet_drop_count=self._value(
                            data,
                            "rx_packet_drop_count",
                            i,
                        ),

                        rx_message_lost_rate=self._value(
                            data,
                            "rx_message_lost_rate",
                            i,
                        ),

                        telemetry_type=self._value(
                            data,
                            "type",
                            i,
                        ),

                        mode=self._value(
                            data,
                            "mode",
                            i,
                        ),

                        mavlink_v2=self._bool_value(
                            data,
                            "mavlink_v2",
                            i,
                        ),

                        flow_control=self._bool_value(
                            data,
                            "flow_control",
                            i,
                        ),

                        forwarding=self._bool_value(
                            data,
                            "forwarding",
                            i,
                        ),

                        ftp=self._bool_value(
                            data,
                            "ftp",
                            i,
                        ),

                        heartbeat_type_gcs=self._bool_value(
                            data,
                            "heartbeat_type_gcs",
                            i,
                        ),

                        heartbeat_type_onboard_controller=self._bool_value(
                            data,
                            "heartbeat_type_onboard_controller",
                            i,
                        ),

                        heartbeat_type_gimbal=self._bool_value(
                            data,
                            "heartbeat_type_gimbal",
                            i,
                        ),

                        heartbeat_type_camera=self._bool_value(
                            data,
                            "heartbeat_type_camera",
                            i,
                        ),

                        heartbeat_component_telemetry_radio=self._bool_value(
                            data,
                            "heartbeat_component_telemetry_radio",
                            i,
                        ),

                        heartbeat_component_log=self._bool_value(
                            data,
                            "heartbeat_component_log",
                            i,
                        ),

                        heartbeat_component_osd=self._bool_value(
                            data,
                            "heartbeat_component_osd",
                            i,
                        ),

                        heartbeat_component_vio=self._bool_value(
                            data,
                            "heartbeat_component_vio",
                            i,
                        ),

                        open_drone_id_system_healthy=self._bool_value(
                            data,
                            "open_drone_id_system_healthy",
                            i,
                        ),

                        parachute_system_healthy=self._bool_value(
                            data,
                            "parachute_system_healthy",
                            i,
                        ),

                        source_platform=self.platform_name,

                        raw=raw,
                    )
                )

        return records

    # ---------------------------------------------------------
    # FAILSAFE
    # ---------------------------------------------------------

    def extract_failsafe(self):
        """
        Extract failsafe_flags into normalized FailsafeRecord objects.
        """

        dataset = self._dataset("failsafe_flags")

        if dataset is None:
            return []

        data = dataset.data
        timestamps = data.get("timestamp", [])

        records = []

        for i in range(len(timestamps)):

            timestamp = self._value(
                data,
                "timestamp",
                i,
            )

            if timestamp is None:
                continue

            raw = {
                "dataset": "failsafe_flags",
                "instance": self._dataset_instance(dataset),
            }

            records.append(
                FailsafeRecord(
                    timestamp=timestamp / 1_000_000.0,

                    angular_velocity_invalid=self._bool_value(
                        data,
                        "angular_velocity_invalid",
                        i,
                    ),

                    attitude_invalid=self._bool_value(
                        data,
                        "attitude_invalid",
                        i,
                    ),

                    local_altitude_invalid=self._bool_value(
                        data,
                        "local_altitude_invalid",
                        i,
                    ),

                    local_position_invalid=self._bool_value(
                        data,
                        "local_position_invalid",
                        i,
                    ),

                    local_velocity_invalid=self._bool_value(
                        data,
                        "local_velocity_invalid",
                        i,
                    ),

                    global_position_invalid=self._bool_value(
                        data,
                        "global_position_invalid",
                        i,
                    ),

                    auto_mission_missing=self._bool_value(
                        data,
                        "auto_mission_missing",
                        i,
                    ),

                    offboard_control_signal_lost=self._bool_value(
                        data,
                        "offboard_control_signal_lost",
                        i,
                    ),

                    home_position_invalid=self._bool_value(
                        data,
                        "home_position_invalid",
                        i,
                    ),

                    manual_control_signal_lost=self._bool_value(
                        data,
                        "manual_control_signal_lost",
                        i,
                    ),

                    gcs_connection_lost=self._bool_value(
                        data,
                        "gcs_connection_lost",
                        i,
                    ),

                    battery_warning=self._value(
                        data,
                        "battery_warning",
                        i,
                    ),

                    battery_low_remaining_time=self._bool_value(
                        data,
                        "battery_low_remaining_time",
                        i,
                    ),

                    battery_unhealthy=self._bool_value(
                        data,
                        "battery_unhealthy",
                        i,
                    ),

                    geofence_breached=self._bool_value(
                        data,
                        "geofence_breached",
                        i,
                    ),

                    mission_failure=self._bool_value(
                        data,
                        "mission_failure",
                        i,
                    ),

                    wind_limit_exceeded=self._bool_value(
                        data,
                        "wind_limit_exceeded",
                        i,
                    ),

                    flight_time_limit_exceeded=self._bool_value(
                        data,
                        "flight_time_limit_exceeded",
                        i,
                    ),

                    position_accuracy_low=self._bool_value(
                        data,
                        "position_accuracy_low",
                        i,
                    ),

                    navigator_failure=self._bool_value(
                        data,
                        "navigator_failure",
                        i,
                    ),

                    critical_failure=self._bool_value(
                        data,
                        "fd_critical_failure",
                        i,
                    ),

                    esc_arming_failure=self._bool_value(
                        data,
                        "fd_esc_arming_failure",
                        i,
                    ),

                    imbalanced_propeller=self._bool_value(
                        data,
                        "fd_imbalanced_prop",
                        i,
                    ),

                    motor_failure=self._bool_value(
                        data,
                        "fd_motor_failure",
                        i,
                    ),

                    source_platform=self.platform_name,

                    raw=raw,
                )
            )

        return records

    # ---------------------------------------------------------
    # COMMANDS
    # ---------------------------------------------------------

    def extract_commands(self):
        """
        Extract vehicle_command records.
        """

        dataset = self._dataset("vehicle_command")

        if dataset is None:
            return []

        data = dataset.data
        timestamps = data.get("timestamp", [])

        records = []

        parameter_fields = [
            "param1",
            "param2",
            "param3",
            "param4",
            "param5",
            "param6",
            "param7",
        ]

        for i in range(len(timestamps)):

            timestamp = self._value(
                data,
                "timestamp",
                i,
            )

            if timestamp is None:
                continue

            parameters = {}

            for field in parameter_fields:
                parameters[field] = self._value(
                    data,
                    field,
                    i,
                )

            records.append(
                CommandRecord(
                    timestamp=timestamp / 1_000_000.0,

                    command_id=self._value(
                        data,
                        "command",
                        i,
                    ),

                    source_system=self._value(
                        data,
                        "source_system",
                        i,
                    ),

                    source_component=self._value(
                        data,
                        "source_component",
                        i,
                    ),

                    target_system=self._value(
                        data,
                        "target_system",
                        i,
                    ),

                    target_component=self._value(
                        data,
                        "target_component",
                        i,
                    ),

                    parameters=parameters,

                    source_platform=self.platform_name,
                )
            )

        return records

    # ---------------------------------------------------------
    # COMMAND ACKS
    # ---------------------------------------------------------

    def extract_command_acks(self):
        """
        Extract vehicle_command_ack records.
        """

        dataset = self._dataset("vehicle_command_ack")

        if dataset is None:
            return []

        data = dataset.data
        timestamps = data.get("timestamp", [])

        records = []

        for i in range(len(timestamps)):

            timestamp = self._value(
                data,
                "timestamp",
                i,
            )

            if timestamp is None:
                continue

            records.append(
                CommandAckRecord(
                    timestamp=timestamp / 1_000_000.0,

                    command_id=self._value(
                        data,
                        "command",
                        i,
                    ),

                    result=self._value(
                        data,
                        "result",
                        i,
                    ),

                    target_system=self._value(
                        data,
                        "target_system",
                        i,
                    ),

                    target_component=self._value(
                        data,
                        "target_component",
                        i,
                    ),

                    source_platform=self.platform_name,
                )
            )

        return records

    # ---------------------------------------------------------
    # VEHICLE STATES
    # ---------------------------------------------------------

    def extract_states(self):
        """
        Extract vehicle_status into normalized StateRecord objects.
        """

        dataset = self._dataset("vehicle_status")

        if dataset is None:
            return []

        data = dataset.data
        timestamps = data.get("timestamp", [])

        records = []

        for i in range(len(timestamps)):

            timestamp = self._value(
                data,
                "timestamp",
                i,
            )

            if timestamp is None:
                continue

            arming_state = self._value(
                data,
                "arming_state",
                i,
            )

            nav_state = self._value(
                data,
                "nav_state",
                i,
            )

            failsafe = self._value(
                data,
                "failsafe",
                i,
            )

            gcs_lost = self._value(
                data,
                "gcs_connection_lost",
                i,
            )

            preflight = self._value(
                data,
                "pre_flight_checks_pass",
                i,
            )

            records.append(
                StateRecord(
                    timestamp=timestamp / 1_000_000.0,

                    armed=(
                        arming_state == 2
                        if arming_state is not None
                        else None
                    ),

                    flight_mode=(
                        str(nav_state)
                        if nav_state is not None
                        else None
                    ),

                    failsafe=(
                        bool(failsafe)
                        if failsafe is not None
                        else None
                    ),

                    gcs_connection_lost=(
                        bool(gcs_lost)
                        if gcs_lost is not None
                        else None
                    ),

                    preflight_checks_pass=(
                        bool(preflight)
                        if preflight is not None
                        else None
                    ),

                    source_platform=self.platform_name,
                )
            )

        return records

    # ---------------------------------------------------------
    # PARAMETERS
    # ---------------------------------------------------------
    def extract_parameters(self) -> list[ParameterRecord]:
        records = []

        for name, value in self.ulog.initial_parameters.items():
            records.append(
                ParameterRecord(
                    timestamp=None,
                    name=str(name),
                    value=value,
                    source_platform=self.platform_name,
                    raw={
                        "source": "ULog.initial_parameters",
                        "parameter_name": str(name),
                        "parameter_value": value,
                    },
                )
            )

        return records

    def extract_platform_metadata(self) -> dict[str, Any]:
     return {
        "sys_name": self.ulog.msg_info_dict.get("sys_name"),
        "sys_os_name": self.ulog.msg_info_dict.get("sys_os_name"),
        "sys_os_ver_release": self.ulog.msg_info_dict.get("sys_os_ver_release"),
        "ver_hw": self.ulog.msg_info_dict.get("ver_hw"),
        "ver_sw": self.ulog.msg_info_dict.get("ver_sw"),
        "ver_sw_branch": self.ulog.msg_info_dict.get("ver_sw_branch"),
        "ver_sw_release": self.ulog.msg_info_dict.get("ver_sw_release"),
        "ver_data_format": self.ulog.msg_info_dict.get("ver_data_format"),
        "sys_toolchain": self.ulog.msg_info_dict.get("sys_toolchain"),
        "sys_toolchain_ver": self.ulog.msg_info_dict.get("sys_toolchain_ver"),
        "time_ref_utc": self.ulog.msg_info_dict.get("time_ref_utc"),
        "boot_time_utc_us": self.ulog.msg_info_dict.get("boot_time_utc_us"),
        "metadata_events_sha256": self.ulog.msg_info_dict.get(
            "metadata_events_sha256"
        ),
     }

    # ---------------------------------------------------------
    # EVENTS
    # ---------------------------------------------------------

    def extract_events(self):
        """
        Extract native PX4 ULog ``event`` records.

        PX4 event IDs are preserved as opaque native identifiers.
        This parser does not attempt to infer human-readable event
        meanings from numeric IDs.

        Native fields preserved:
        - timestamp
        - id
        - event_sequence
        - arguments[0..24]
        - log_levels

        The complete native record is also preserved in ``raw``.
        """

        events = []

        datasets = [
            dataset
            for dataset in self.ulog.data_list
            if dataset.name == "event"
        ]

        for dataset in datasets:
            data = dataset.data

            timestamps = data.get("timestamp", [])
            event_ids = data.get("id", [])
            sequences = data.get("event_sequence", [])
            log_levels = data.get("log_levels", [])

            argument_fields = [
                f"arguments[{index}]"
                for index in range(25)
                if f"arguments[{index}]" in data
            ]

            count = len(timestamps)

            for index in range(count):
                timestamp_us = int(timestamps[index])
                event_id = int(event_ids[index])

                event_sequence = (
                    int(sequences[index])
                    if index < len(sequences)
                    else None
                )

                log_level = (
                    int(log_levels[index])
                    if index < len(log_levels)
                    else None
                )

                arguments = {}

                for field_name in argument_fields:
                    values = data[field_name]

                    if index < len(values):
                        value = values[index]

                        if hasattr(value, "item"):
                            value = value.item()

                        arguments[field_name] = value

                raw = {
                    "timestamp_us": timestamp_us,
                    "id": event_id,
                    "event_sequence": event_sequence,
                    "log_levels": log_level,
                    "arguments": arguments,
                    "dataset": dataset.name,
                    "multi_id": dataset.multi_id,
                }

                events.append(
                    ForensicEvent(
                        timestamp=timestamp_us / 1_000_000.0,
                        event_type="PX4_EVENT",
                        description=(
                            f"PX4 native event ID {event_id}"
                        ),
                        source_platform=self.platform_name,
                        severity=None,
                        data={
                            "event_id": event_id,
                            "event_sequence": event_sequence,
                            "log_levels": log_level,
                            "arguments": arguments,
                        },
                        raw=raw,
                    )
                )

        return events
