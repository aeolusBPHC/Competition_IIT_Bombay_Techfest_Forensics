"""Shared forensic mappings over decoded Blackbox I/P/G/H/S/E frames."""
import math
import re
from platform_parsers.common.evidence_model import (
    BatteryRecord, ForensicEvent, NavigationRecord, ParameterRecord, StateRecord, FailsafeRecord,
    TelemetryRecord, TrajectoryRecord,
)
from platform_parsers.emuflight.blackbox_decoder import decode_file


class BlackboxEvidenceMixin:
    UNSUPPORTED_CATEGORIES = {
        'commands': 'Blackbox has no MAVLink-style command protocol.',
        'command_acks': 'Blackbox has no command acknowledgement protocol.',
    }

    def _blackbox_logs(self):
        if self.platform_name == 'EmuFlight':
            return self._load()
        if not hasattr(self, '_decoded_blackbox_logs'):
            self._decoded_blackbox_logs = decode_file(str(self.evidence_path))
        return self._decoded_blackbox_logs

    @staticmethod
    def _blackbox_raw(frame, log, kind):
        return {**{key: value for key, value in frame.items() if not key.startswith('_')},
                'frame_type': kind, 'file_offset': frame.get('_file_offset'), 'log_index': log.index}

    @staticmethod
    def _blackbox_time(frame):
        time = frame.get('time', frame.get('current_time_us', frame.get('time_us', frame.get('_last_main_time'))))
        return time / 1e6 if time is not None else None

    def _enrich_blackbox_metadata(self, metadata):
        logs = self._blackbox_logs()
        times = [time for log in logs for group in (log.main_frames, log.gps_frames)
                 for frame in group if (time := self._blackbox_time(frame)) is not None]
        metadata.source_file = str(self.evidence_path)
        metadata.start_time = min(times) if times else None
        metadata.end_time = max(times) if times else None
        metadata.duration = max(times) - min(times) if times else None
        metadata.metadata['decoded_logs'] = [
            {'log_index': log.index, 'file_offset': log.file_offset, 'decode_stats': log.stats.as_dict()}
            for log in logs
        ]
        metadata.metadata['time_base'] = 'seconds since flight-controller boot; log_index distinguishes sessions'
        return metadata

    def _iter_complete_gps_frames(self):
        for log in self._blackbox_logs():
            for frame in log.gps_frames:
                values = {key: value for key, value in frame.items() if not key.startswith('_')}
                if 'time' not in values and frame.get('_last_main_time') is not None:
                    values['time'] = frame['_last_main_time']
                if 'time' not in values:
                    continue
                yield {'values': values, 'frame_type': 'G', 'raw_offset': frame['_file_offset'], 'log_index': log.index}

    def _iter_complete_main_frames(self):
        for log in self._blackbox_logs():
            for frame in log.main_frames:
                if self._blackbox_time(frame) is not None:
                    yield {'values': {key: value for key, value in frame.items() if not key.startswith('_')},
                           'frame_type': frame['_frame_type'], 'raw_offset': frame['_file_offset'], 'log_index': log.index}

    def extract_states(self):
        result = []
        keys = ('flightModeFlags', 'stateFlags', 'failsafePhase', 'rxSignalReceived', 'rxFlightChannelsValid')
        for log in self._blackbox_logs():
            previous = None
            items = [(frame.get('_file_offset', 0), frame, frame.get('_frame_type', 'S'))
                     for frame in [*log.main_frames, *log.slow_frames] if any(key in frame for key in keys)]
            items.extend((event.get('_file_offset', 0), event, 'E') for event in log.events
                         if event['event_type'] in (15, 30))
            for _, frame, kind in sorted(items, key=lambda item: item[0]):
                timestamp = self._blackbox_time(frame)
                if timestamp is None:
                    continue
                key = tuple(frame.get(name) for name in keys)
                if kind != 'E' and key == previous:
                    continue
                if kind != 'E':
                    previous = key
                flags = frame.get('flightModeFlags', frame.get('flags'))
                phase = frame.get('failsafePhase')
                result.append(StateRecord(
                    timestamp=timestamp, armed=False if kind == 'E' and frame['event_type'] == 15 else None,
                    flight_mode=f'0x{flags:08X}' if flags is not None else None,
                    failsafe=phase != 0 if phase is not None else None,
                    source_platform=self.platform_name, raw=self._blackbox_raw(frame, log, kind),
                ))
        return result

    def extract_failsafe(self):
        result = []
        for log in self._blackbox_logs():
            previous = None
            frames = sorted([*log.main_frames, *log.slow_frames], key=lambda frame: frame['_file_offset'])
            for frame in frames:
                if not any(name in frame for name in ('failsafePhase', 'rxSignalReceived', 'rxFlightChannelsValid', 'navFlags')):
                    continue
                key = tuple(frame.get(name) for name in ('failsafePhase', 'rxSignalReceived', 'rxFlightChannelsValid', 'navFlags'))
                timestamp = self._blackbox_time(frame)
                if timestamp is None or key == previous:
                    continue
                previous = key
                rx = frame.get('rxSignalReceived')
                nav = frame.get('navFlags') if self.platform_name == 'INAV' else None
                result.append(FailsafeRecord(
                    timestamp=timestamp, manual_control_signal_lost=(rx == 0) if rx is not None else None,
                    failsafe_phase=frame.get('failsafePhase'),
                    failsafe_active=bool(frame['failsafePhase']) if 'failsafePhase' in frame else None,
                    local_position_invalid=not bool(nav & 4) if nav is not None else None,
                    local_altitude_invalid=not bool(nav & 1) if nav is not None else None,
                    source_platform=self.platform_name,
                    raw=self._blackbox_raw(frame, log, frame.get('_frame_type', 'S')),
                ))
        return result

    def extract_telemetry(self):
        result = []
        for log in self._blackbox_logs():
            for frame in [*log.main_frames, *log.slow_frames]:
                timestamp = self._blackbox_time(frame)
                if timestamp is not None and 'rssi' in frame:
                    result.append(TelemetryRecord(timestamp=timestamp, rc_signal_strength_raw=frame['rssi'],
                                                   source_platform=self.platform_name,
                                                   raw=self._blackbox_raw(frame, log, frame.get('_frame_type', 'S'))))
        return result

    def extract_parameters(self):
        result = []
        for log in self._blackbox_logs():
            for key, value in log.headers.items():
                if key.startswith(('Field ', 'Product', 'Data version', 'I interval', 'P interval', 'P ratio')):
                    continue
                result.append(ParameterRecord(None, key, value, source_platform=self.platform_name,
                                               raw={'header': key, 'value': value, 'log_index': log.index,
                                                    'file_offset': log.file_offset}))
        return result

    def extract_events(self):
        result = []
        for log in self._blackbox_logs():
            for event in log.events:
                timestamp = self._blackbox_time(event)
                if timestamp is None:
                    continue
                result.append(ForensicEvent(timestamp=timestamp,
                    event_type=event.get('event_name') or f"UNKNOWN_{event['event_type']}",
                    description=f"{self.platform_name} Blackbox event",
                    source_platform=self.platform_name,
                    data={key: value for key, value in event.items() if not key.startswith('_')},
                    raw=self._blackbox_raw(event, log, 'E')))
        return result

    def extract_trajectory(self):
        if self.platform_name != 'INAV':
            return []  # A GPS trace or body acceleration is not a native metric estimator trajectory.
        result = []
        for log in self._blackbox_logs():
            for frame in log.main_frames:
                if not any(f'navPos[{axis}]' in frame for axis in range(3)):
                    continue
                timestamp = self._blackbox_time(frame)
                if timestamp is None:
                    continue
                def scaled(name):
                    value = frame.get(name)
                    return value / 100.0 if value is not None else None
                # INAV navigation is north/east/up in cm and cm/s. Do not
                # negate z as would be required for a NED source.
                position = [scaled('navPos[1]'), scaled('navPos[0]'), scaled('navPos[2]')]
                velocity = [scaled('navVel[1]'), scaled('navVel[0]'), scaled('navVel[2]')]
                flags = frame.get('navFlags')
                hp = flags is not None and bool(flags & 4) and all(v is not None for v in position[:2])
                vp = flags is not None and bool(flags & 1) and position[2] is not None
                hv = hp and all(v is not None for v in velocity[:2])
                vv = vp and velocity[2] is not None
                result.append(TrajectoryRecord(
                    timestamp=timestamp, x_m=position[0], y_m=position[1], z_m=position[2],
                    vx_m_s=velocity[0], vy_m_s=velocity[1], vz_m_s=velocity[2],
                    position_valid=hp and vp, horizontal_position_valid=hp, vertical_position_valid=vp,
                    velocity_valid=hv and vv, horizontal_velocity_valid=hv, vertical_velocity_valid=vv,
                    position_source='native', velocity_source='native',
                    position_reset_counter=log.index, vertical_reset_counter=log.index,
                    source_platform=self.platform_name, raw=self._blackbox_raw(frame, log, frame['_frame_type']),
                ))
        return result

    def extract_battery(self):
        result = []
        for log in self._blackbox_logs():
            revision = log.headers.get('Firmware revision', '')
            match = re.search(r'(?:INAV\s*)?(\d+)\.', revision, re.I)
            verified = self.platform_name == 'INAV' and match is not None and int(match.group(1)) >= 7
            for frame in log.main_frames:
                timestamp = self._blackbox_time(frame)
                if timestamp is None or not any(key in frame for key in ('vbat', 'amperage')):
                    continue
                if not verified:
                    continue  # Raw readings stay in source_record_groups until units are known.
                result.append(BatteryRecord(timestamp=timestamp,
                    voltage_v=frame['vbat'] / 100.0 if 'vbat' in frame else None,
                    current_a=frame['amperage'] / 100.0 if 'amperage' in frame else None,
                    source_platform=self.platform_name, raw=self._blackbox_raw(frame, log, frame['_frame_type'])))
        return result

    def extract_additional_data(self):
        groups = {name: [] for name in ('main_frames', 'slow_frames', 'home_frames', 'gps_frames', 'events')}
        logs = []
        for log in self._blackbox_logs():
            for name, kind in (('main_frames', 'I/P'), ('slow_frames', 'S'), ('home_frames', 'H'),
                               ('gps_frames', 'G'), ('events', 'E')):
                groups[name].extend(self._blackbox_raw(frame, log, frame.get('_frame_type', kind))
                                    for frame in getattr(log, name))
            logs.append({'log_index': log.index, 'file_offset': log.file_offset,
                         'headers': log.headers, 'decode_stats': log.stats.as_dict()})
        inventory = {}
        for log in self._blackbox_logs():
            for name, records in (('I/P', log.main_frames), ('S', log.slow_frames),
                                  ('G', log.gps_frames), ('H', log.home_frames), ('E', log.events)):
                item = inventory.setdefault(name, {'record_count': 0, 'fields': set()})
                item['record_count'] += len(records)
                item['fields'].update(key for record in records for key in record if not key.startswith('_'))
        for item in inventory.values():
            item['fields'] = sorted(item['fields'])
        return {'source_record_groups': groups, 'blackbox_logs': logs, 'message_inventory': inventory,
                'raw_field_units': 'Native firmware units; calibration headers are retained. Unknown units are not converted.'}
