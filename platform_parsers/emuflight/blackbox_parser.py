"""
EmuFlight Blackbox parser.

Layering (matches the rest of the toolkit):
    blackbox_decoder.py  -> bytes to generic frames (no forensic meaning)
    this module          -> EmuFlight-specific identification + mapping
                            into platform_parsers.common.evidence_model

Evidence rules applied here:
    * A field the log does not contain stays None; nothing is estimated.
    * Unit conversions whose scale has NOT been verified for EmuFlight are
      disabled by default (see EmuFlightUnitConfig) and the raw integer is
      kept in record.raw, so nothing is silently mis-scaled.
    * Every record's raw dict carries the byte offset of its source frame
      and the log index inside the file, so any value can be traced back
      to the hashed original.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from platform_parsers.common import evidence_model as em
from platform_parsers.common.evidence_model import ParameterRecord
from platform_parsers.common.base_parser import BaseForensicParser
from platform_parsers.emuflight.blackbox_decoder import (
    EVENT_DISARM,
    EVENT_FLIGHT_MODE,
    LOG_START_MARKER,
    BlackboxLog,
    decode_file,
    parse_headers,
)

PLATFORM = "EmuFlight"
FORMAT = "Blackbox"

# Headers that describe the log structure rather than vehicle configuration.
_STRUCTURAL_HEADER_PREFIXES = ("Field ", "Product", "Data version", "I interval",
                               "P interval", "P ratio")


@dataclass(frozen=True)
class EmuFlightUnitConfig:
    """
    Scale factors from raw Blackbox integers to engineering units.

    Status of each default:
      time_scale_s          1e-6   Blackbox 'time' is microseconds since boot
                                   (stable across the Cleanflight lineage).
      coordinate_scale_deg  1e-7   GPS_coord is degrees x 1e7 (stable).
      gps_speed_scale_m_s   0.01   cm/s in Betaflight lineage. ASSUMED for
                                   EmuFlight; confirm on a real log.
      gps_course_scale_deg  0.1    decidegrees in Betaflight lineage. ASSUMED.
      gps_altitude_scale_m  None   The altitude unit changed between
                                   Betaflight-lineage versions. Disabled
                                   until verified against a known altitude.
      vbat_scale_v          None   vbatLatest units depend on firmware
                                   version. Disabled until verified.
      amperage_scale_a      None   Same as above.

    A None scale means the normalized field stays None and the raw integer
    is preserved in record.raw.
    """
    time_scale_s: float = 1e-6
    coordinate_scale_deg: float = 1e-7
    gps_speed_scale_m_s: float | None = 0.01
    gps_course_scale_deg: float | None = 0.1
    gps_altitude_scale_m: float | None = None
    vbat_scale_v: float | None = None
    amperage_scale_a: float | None = None

    def assumptions(self) -> dict[str, Any]:
        verified = {"time_scale_s", "coordinate_scale_deg"}
        out = {}
        for key, value in asdict(self).items():
            if value is None:
                status = "disabled_unit_not_verified"
            elif key in verified:
                status = "format_convention"
            else:
                status = "assumed_from_betaflight_lineage"
            out[key] = {"value": value, "status": status}
        return out


def _scaled(value: Any, scale: float | None) -> float | None:
    if value is None or scale is None:
        return None
    return value * scale


class EmuFlightBlackboxParser(BaseForensicParser):
    platform_name = PLATFORM
    format_name = FORMAT
    supported_formats = {FORMAT}
    PLATFORM = PLATFORM
    FORMAT = FORMAT
    HEADER_SNIFF_BYTES = 64 * 1024

    def __init__(self, path: str | Path, log_index: int | None = None,
                 units: EmuFlightUnitConfig | None = None):
        """
        log_index: None parses every log in the file (one per arming);
                   an int restricts parsing to that log.
        """
        super().__init__(path)

        self.path = str(self.evidence_path)
        self.log_index = log_index
        self.units = units or EmuFlightUnitConfig()
        self._logs: list[BlackboxLog] | None = None

    # ================================================================ identify
    @classmethod
    def identify(cls, path: str | Path) -> dict[str, Any]:
        result = {"supported": False, "platform": PLATFORM, "format": FORMAT,
                  "confidence": "NONE", "reason": "", "indicators": {}}
        try:
            with open(path, "rb") as fh:
                head = fh.read(cls.HEADER_SNIFF_BYTES)
        except OSError as exc:
            result["reason"] = f"Could not read file: {exc}"
            return result

        start = head.find(LOG_START_MARKER)
        if start == -1:
            result["reason"] = "No Blackbox product header found"
            return result

        headers, _ = parse_headers(head[start:])
        revision = headers.get("Firmware revision", "")
        fw_type = headers.get("Firmware type", "")
        result["indicators"] = {
            "blackbox_header_offset": start,
            "firmware_type": fw_type or None,
            "firmware_revision": revision or None,
            "data_version": headers.get("Data version"),
        }

        if "emuflight" in revision.lower() or "emuflight" in fw_type.lower():
            result.update(supported=True, confidence="HIGH",
                          reason="Blackbox header with EmuFlight firmware revision detected")
        else:
            result["reason"] = (f"Blackbox log from a different firmware "
                                f"(revision: {revision or 'not recorded'})")
        return result

    # ================================================================ decoding
    def _load(self) -> list[BlackboxLog]:
        if self._logs is None:
            logs = decode_file(self.path)
            if self.log_index is not None:
                logs = [log for log in logs if log.index == self.log_index]
            self._logs = logs
        return self._logs

    def _time_s(self, time_us: int | None) -> float | None:
        return None if time_us is None else time_us * self.units.time_scale_s

    @staticmethod
    def _raw(frame: dict[str, Any], log: BlackboxLog, frame_type: str) -> dict[str, Any]:
        raw = {k: v for k, v in frame.items() if not k.startswith("_")}
        raw["blackbox_frame_type"] = frame_type
        raw["file_offset"] = frame.get("_file_offset")
        raw["log_index"] = log.index
        return raw

    # =============================================================== metadata
    def get_metadata(self) -> em.EvidenceMetadata:
        logs = self._load()
        first = logs[0].headers if logs else {}
        revision = first.get("Firmware revision")
        version = None
        if revision:
            match = re.search(r"EmuFlight\s+v?(\d+(?:\.\d+)+)", revision, re.IGNORECASE)
            version = match.group(1) if match else None

        times = [f["time"] for log in logs for f in log.main_frames if "time" in f]
        start = self._time_s(min(times)) if times else None
        end = self._time_s(max(times)) if times else None

        per_log = []
        for log in logs:
            t = [f["time"] for f in log.main_frames if "time" in f]
            per_log.append({
                "log_index": log.index,
                "file_offset": log.file_offset,
                "start_time_s": self._time_s(min(t)) if t else None,
                "end_time_s": self._time_s(max(t)) if t else None,
                "log_start_datetime": log.headers.get("Log start datetime"),
                "decode_stats": log.stats.as_dict(),
            })

        return em.EvidenceMetadata(
            source_file=self.path,
            platform=PLATFORM,
            format=FORMAT,
            firmware="EmuFlight",
            firmware_version=version,
            vehicle_type=None,  # not recorded in Blackbox headers; not assumed
            start_time=start,
            end_time=end,
            duration=(end - start) if start is not None and end is not None else None,
            metadata={
                "firmware_revision": revision,
                "board_information": first.get("Board information"),
                "craft_name": first.get("Craft name"),
                "data_version": first.get("Data version"),
                "log_count": len(logs),
                "logs": per_log,
                "time_base": "seconds since flight-controller boot",
                "overlapping_log_time_ranges": self._logs_overlap(per_log),
                "unit_assumptions": self.units.assumptions(),
            },
        )

    @staticmethod
    def _logs_overlap(per_log: list[dict[str, Any]]) -> bool:
        spans = sorted((p["start_time_s"], p["end_time_s"]) for p in per_log
                       if p["start_time_s"] is not None)
        return any(spans[i + 1][0] < spans[i][1] for i in range(len(spans) - 1))

    # ------------------------------------------------------------------
    # Backward-compatible metadata API
    # ------------------------------------------------------------------

    def extract_metadata(self) -> em.EvidenceMetadata:
        """
        Backward-compatible alias for get_metadata().

        The common parser contract uses get_metadata(), while older
        EmuFlight-specific callers use extract_metadata().
        """
        return self.get_metadata()

    # ==================================================================== GPS
    def extract_gps(self) -> list[em.GPSRecord]:
        u = self.units
        records = []
        for log in self._load():
            for frame in log.gps_frames:
                time_us = frame.get("time", frame.get("_last_main_time"))
                if time_us is None:
                    continue
                lat = frame.get("GPS_coord[0]")
                lon = frame.get("GPS_coord[1]")
                sats = frame.get("GPS_numSat")
                records.append(em.GPSRecord(
                    timestamp=self._time_s(time_us),
                    latitude=_scaled(lat, u.coordinate_scale_deg),
                    longitude=_scaled(lon, u.coordinate_scale_deg),
                    altitude_m=_scaled(frame.get("GPS_altitude"), u.gps_altitude_scale_m),
                    speed_m_s=_scaled(frame.get("GPS_speed"), u.gps_speed_scale_m_s),
                    satellites=int(sats) if sats is not None else None,
                    heading_deg=_scaled(frame.get("GPS_ground_course"), u.gps_course_scale_deg),
                    source_platform=PLATFORM,
                    raw=self._raw(frame, log, "G"),
                ))
        return records

    # ============================================================ navigation
    def extract_navigation(self) -> list:
        # Blackbox logs no fused position estimate, so there is nothing
        # to map. Returning [] (not synthesized values) is deliberate.
        return []

    # ================================================================ battery
    def extract_battery(self) -> list[em.BatteryRecord]:
        u = self.units
        if u.vbat_scale_v is None and u.amperage_scale_a is None:
            return []  # units unverified; raw values remain in the main frames
        records = []
        for log in self._load():
            for frame in log.main_frames:
                if "vbatLatest" not in frame and "amperageLatest" not in frame:
                    continue
                records.append(em.BatteryRecord(
                    timestamp=self._time_s(frame.get("time")),
                    voltage_v=_scaled(frame.get("vbatLatest"), u.vbat_scale_v),
                    current_a=_scaled(frame.get("amperageLatest"), u.amperage_scale_a),
                    source_platform=PLATFORM,
                    raw={"vbatLatest": frame.get("vbatLatest"),
                         "amperageLatest": frame.get("amperageLatest"),
                         "file_offset": frame.get("_file_offset"),
                         "log_index": log.index},
                ))
        return records

    # ========================================================= states / failsafe
    _SLOW_STATE_FIELDS = ("flightModeFlags", "stateFlags", "failsafePhase",
                          "rxSignalReceived", "rxFlightChannelsValid")

    def extract_states(self) -> list[em.StateRecord]:
        """
        One StateRecord per change in ANY slow-frame state field (all
        fields are compared, so no transition is collapsed), plus one per
        DISARM / FLIGHT_MODE event.

        armed is only set where the log proves it (DISARM -> False).
        Flight-mode bits are reported as hex; EmuFlight's bit-to-name
        table is not assumed.
        """
        records = []
        for log in self._load():
            items = [("S", f.get("_last_main_time"), f) for f in log.slow_frames]
            items += [("E", e.get("_last_main_time"), e) for e in log.events
                      if e["event_type"] in (EVENT_DISARM, EVENT_FLIGHT_MODE)]
            items.sort(key=lambda it: (it[1] is None, it[1] or 0, it[2].get("_file_offset", 0)))

            last_key = None
            for kind, time_us, item in items:
                if time_us is None:
                    continue
                if kind == "S":
                    key = tuple(item.get(k) for k in self._SLOW_STATE_FIELDS)
                    if key == last_key:
                        continue
                    last_key = key
                    flags = item.get("flightModeFlags")
                    phase = item.get("failsafePhase")
                    records.append(em.StateRecord(
                        timestamp=self._time_s(time_us),
                        flight_mode=f"0x{flags:08X}" if flags is not None else None,
                        failsafe=(phase != 0) if phase is not None else None,
                        source_platform=PLATFORM,
                        raw=self._raw(item, log, "S"),
                    ))
                elif item["event_type"] == EVENT_DISARM:
                    records.append(em.StateRecord(
                        timestamp=self._time_s(time_us), armed=False,
                        source_platform=PLATFORM,
                        raw={**self._raw(item, log, "E"), "disarm_reason_code": item.get("reason")},
                    ))
                else:
                    flags = item.get("flags")
                    records.append(em.StateRecord(
                        timestamp=self._time_s(time_us),
                        flight_mode=f"0x{flags:08X}" if flags is not None else None,
                        source_platform=PLATFORM,
                        raw=self._raw(item, log, "E"),
                    ))
        return records

    def extract_failsafe(self) -> list[em.FailsafeRecord]:
        records = []
        for log in self._load():
            last_key = None
            for frame in log.slow_frames:
                time_us = frame.get("_last_main_time")
                if time_us is None:
                    continue
                key = (frame.get("failsafePhase"), frame.get("rxSignalReceived"),
                       frame.get("rxFlightChannelsValid"))
                if key == last_key:
                    continue
                last_key = key
                rx = frame.get("rxSignalReceived")
                records.append(em.FailsafeRecord(
                    timestamp=self._time_s(time_us),
                    manual_control_signal_lost=(rx == 0) if rx is not None else None,
                    source_platform=PLATFORM,
                    raw=self._raw(frame, log, "S"),
                ))
        return records

    # ============================================ categories Blackbox lacks
    def extract_telemetry(self) -> list:
        return []

    def extract_commands(self) -> list:
        return []  # Blackbox has no command/ACK protocol

    def extract_command_acks(self) -> list:
        return []

    # ============================================== parameters and events
    def extract_parameters(self) -> list[ParameterRecord]:
        """
        Extract Blackbox configuration headers as normalized
        ParameterRecord objects.

        Structural Blackbox headers are excluded because they describe
        the log/container rather than flight-controller configuration.
        """
        params = []

        for log in self._load():
            for name, value in log.headers.items():
                if name.startswith(_STRUCTURAL_HEADER_PREFIXES):
                    continue

                params.append(
                    ParameterRecord(
                        timestamp=None,
                        name=str(name),
                        value=value,
                        source_platform=self.platform_name,
                        raw={
                            "source": "EmuFlight.Blackbox.header",
                            "parameter_name": str(name),
                            "parameter_value": value,
                            "log_index": log.index,
                        },
                    )
                )

        return params

    def extract_events(self) -> list[em.ForensicEvent]:
        """
        Extract decoded EmuFlight Blackbox events as normalized
        ForensicEvent records.

        Native Blackbox fields are preserved in ``data`` and ``raw`` so
        normalization does not discard forensic evidence.
        """
        events = []

        for log in self._load():
            for e in log.events:
                timestamp = self._time_s(e.get("_last_main_time"))
                event_type = (
                    e.get("event_name")
                    or f"UNKNOWN_{e.get('event_type', 'UNKNOWN')}"
                )

                data = {
                    k: v
                    for k, v in e.items()
                    if not k.startswith("_")
                }

                raw = {
                    k: v
                    for k, v in e.items()
                    if not k.startswith("_")
                }

                # Preserve parser-internal provenance fields separately.
                raw.update({
                    "file_offset": e.get("_file_offset"),
                    "log_index": log.index,
                })

                events.append(
                    em.ForensicEvent(
                        timestamp=timestamp,
                        event_type=str(event_type),
                        description=(
                            f"EmuFlight Blackbox event: {event_type}"
                        ),
                        source_platform=self.platform_name,
                        severity=None,
                        data=data,
                        raw=raw,
                    )
                )

        return events

    # ============================================================= normalize
    def normalize(self):
        """
        Build the toolkit's NormalizedEvidence object.

        ALIGN WITH YOUR REPO: the handoff notes do not show the
        NormalizedEvidence constructor or the parameter/event record
        classes. Copy the equivalent method from the Betaflight parser and
        keep the extract_* calls below.
        """
        normalized_cls = getattr(em, "NormalizedEvidence", None)
        payload = {
            "metadata": self.extract_metadata(),
            "gps": self.extract_gps(),
            "navigation": self.extract_navigation(),
            "battery": self.extract_battery(),
            "telemetry": self.extract_telemetry(),
            "failsafe": self.extract_failsafe(),
            "commands": self.extract_commands(),
            "command_acks": self.extract_command_acks(),
            "states": self.extract_states(),
            "parameters": self.extract_parameters(),
            "events": self.extract_events(),
        }
        return normalized_cls(**payload) if normalized_cls else payload
