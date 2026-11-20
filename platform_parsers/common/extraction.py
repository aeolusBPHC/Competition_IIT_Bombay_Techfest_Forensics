"""Evidence coverage and JSON-safe preservation of decoded source observations."""
from collections import Counter
from dataclasses import fields, is_dataclass
import math

CATEGORIES = ("gps", "navigation", "trajectory", "battery", "telemetry", "failsafe",
              "commands", "command_acks", "states", "parameters", "events")


def json_value(value):
    if is_dataclass(value):
        # Avoid deepcopying large raw dictionaries already held by evidence.
        return {field.name: json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        converted = {str(key): json_value(item) for key, item in value.items()}
        return value if all(isinstance(key, str) and converted[key] is item
                            for key, item in value.items()) else converted
    if isinstance(value, (tuple, list)):
        converted = [json_value(item) for item in value]
        return value if isinstance(value, list) and all(new is old for new, old in zip(converted, value)) else converted
    if isinstance(value, bytes):
        return {"encoding": "hex", "value": value.hex()}
    if hasattr(value, "tolist"):
        return json_value(value.tolist())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def coverage(evidence, parser):
    unavailable = getattr(parser, "UNSUPPORTED_CATEGORIES", {})
    inventory = evidence.additional_data.get("message_inventory", {})
    observed = {name.split("[", 1)[0] for name, item in inventory.items() if item.get("record_count")}
    observed_fields = {field for item in inventory.values() for field in item.get("fields", [])}
    if evidence.metadata.format.upper() == "TLOG":
        sources = {
            "gps": ["GPS_RAW_INT", "GPS2_RAW", "GLOBAL_POSITION_INT"], "navigation": ["GLOBAL_POSITION_INT"],
            "trajectory": ["LOCAL_POSITION_NED", "LOCAL_POSITION_NED_COV", "ODOMETRY"],
            "battery": ["SYS_STATUS", "BATTERY_STATUS"], "telemetry": ["RADIO_STATUS", "SYS_STATUS"],
            "failsafe": ["ESTIMATOR_STATUS", "EKF_STATUS_REPORT", "FENCE_STATUS", "SYS_STATUS", "HEARTBEAT", "STATUSTEXT"],
            "states": ["HEARTBEAT", "EXTENDED_SYS_STATE", "SYS_STATUS"],
            "commands": ["COMMAND_LONG", "COMMAND_INT"], "command_acks": ["COMMAND_ACK"],
            "parameters": ["PARAM_VALUE", "PARAM_SET", "PARAM_EXT_VALUE", "PARAM_EXT_SET"], "events": ["STATUSTEXT"],
        }
        required_fields = {}
    elif evidence.metadata.format.upper() == "DATAFLASH":
        sources = {
            "gps": ["GPS", "GPS2"], "navigation": ["POS"], "trajectory": ["XKF1", "NKF1"],
            "battery": ["BAT", "BAT2", "BAT3", "BAT4", "BCL"], "telemetry": ["RAD"],
            "failsafe": ["ERR", "XKF4", "NKF4"], "states": ["MODE", "ARM"],
            "commands": ["MAVC"], "parameters": ["PARM"], "events": ["EV", "ERR", "MSG"],
        }
        required_fields = {}
    elif evidence.metadata.platform == "PX4":
        sources = {
            "gps": ["vehicle_gps_position", "sensor_gps"], "navigation": ["vehicle_global_position"],
            "trajectory": ["vehicle_local_position"], "battery": ["battery_status"], "telemetry": ["telemetry_status"],
            "failsafe": ["failsafe_flags"], "states": ["vehicle_status"], "commands": ["vehicle_command"],
            "command_acks": ["vehicle_command_ack"], "parameters": ["initial_parameters"],
            "events": ["event", "logged_messages"],
        }
        required_fields = {}
    else:
        sources = {"gps": ["G"], "navigation": ["G"], "trajectory": ["I/P"], "battery": ["I/P"],
                   "telemetry": ["I/P", "S"], "failsafe": ["I/P", "S"], "states": ["I/P", "S", "E"],
                   "parameters": ["headers"], "events": ["E"]}
        required_fields = {"trajectory": ["navPos[0]", "navPos[1]", "navPos[2]"],
                           "battery": ["vbatLatest", "amperageLatest", "vbat", "amperage"],
                           "telemetry": ["rssi"], "failsafe": ["failsafePhase", "rxSignalReceived", "navFlags"]}
    logs = evidence.additional_data.get("blackbox_logs", [])
    incomplete = any(
        stats.get("frames_corrupt") or stats.get("truncated_at_end") or stats.get("p_frames_without_history")
        or stats.get("gps_frames_without_home") or stats.get("bytes_skipped_resync")
        for stats in [log.get("decode_stats", {}) for log in logs]
    )
    stats = evidence.additional_data.get("decode_stats", {})
    incomplete |= bool(stats.get("errors") or stats.get("truncated_at_end"))
    result = {}
    for category in CATEGORIES:
        records = getattr(evidence, category)
        populated = Counter()
        names = [field.name for field in fields(records[0])
                 if field.name not in {"raw", "timestamp", "source_platform"}] if records else []
        for record in records:
            for name in names:
                if getattr(record, name) is not None:
                    populated[name] += 1
        expected = sources.get(category, [])
        present = sorted(observed.intersection(expected))
        missing_fields = category in required_fields and not observed_fields.intersection(required_fields[category])
        result[category] = {
            "record_count": len(records), "populated_fields": dict(populated),
            "status": ("extracted" if records else "unsupported" if category in unavailable
                       else "decode_incomplete" if incomplete else "not_recorded" if not present or missing_fields
                       else "source_present_no_normalized_records"),
            "expected_sources": expected, "recorded_sources": present,
            "decoder_incomplete": bool(incomplete),
            "note": unavailable.get(category) if not records else None,
        }
    return result
