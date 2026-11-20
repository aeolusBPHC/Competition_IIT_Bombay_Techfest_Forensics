"""DataFlash mappings for native EKF state, link statistics and explicit failsafes."""
from collections import Counter, defaultdict
import math
from platform_parsers.common.evidence_model import TrajectoryRecord, TelemetryRecord, FailsafeRecord, BatteryRecord


def fields(record):
    return dict(zip(record['labels'], record['values']))


def raw(record):
    return {'dataset': record['name'], 'message_type': record['message_type'],
            'format': record['format'], 'file_offset': record['offset'],
            'fields': fields(record), 'raw_fields': dict(zip(record['labels'], record['raw_values']))}


def finite(value):
    return value is not None and isinstance(value, (int, float)) and math.isfinite(value)


class DataFlashEvidenceMixin:
    UNSUPPORTED_CATEGORIES = {'command_acks': 'DataFlash MAVC commands are not command acknowledgements.'}

    def extract_trajectory(self):
        records = list(self._iter_records())
        counts = Counter((record['name'], fields(record).get('C', 0)) for record in records
                         if record['name'] in {'XKF1', 'NKF1'})
        if not counts:
            return []
        # One filter family/core per canonical trajectory; alternatives are retained raw.
        family, core = min(counts, key=lambda key: (key[0] != 'XKF1', -counts[key], key[1]))
        status_name = 'XKF4' if family == 'XKF1' else 'NKF4'
        status, status_time, last_time, reset, last_offset = {}, None, None, 0, None
        result = []
        for record in records:
            values = fields(record)
            timestamp = self._timestamp(values)
            if timestamp is None:
                continue
            if record['name'] not in {family, status_name} or values.get('C', 0) != core:
                continue
            if last_time is not None and timestamp < last_time:
                reset += 1
                status, status_time, last_offset = {}, None, None
            last_time = timestamp
            if record['name'] == status_name and values.get('C', 0) == core:
                offset = (values.get('OFN'), values.get('OFE'))
                if last_offset is not None and offset != last_offset:
                    reset += 1
                if any(value is not None for value in offset):
                    last_offset = offset
                status, status_time = values, timestamp
            if record['name'] != family or values.get('C', 0) != core:
                continue
            solution = status.get('SS')
            # If no explicit solution status is logged, keep the observations
            # but do not certify position/velocity validity for ML.
            hp = solution is not None and bool(solution & (8 | 16))
            vp = solution is not None and bool(solution & 32)
            hv = solution is not None and bool(solution & 2)
            vv = solution is not None and bool(solution & 4)
            position = [values.get('PE'), values.get('PN'), -values['PD'] if finite(values.get('PD')) else None]
            velocity = [values.get('VE'), values.get('VN'), -values['VD'] if finite(values.get('VD')) else None]
            hp &= all(finite(value) for value in position[:2])
            vp &= finite(position[2])
            hv &= all(finite(value) for value in velocity[:2])
            vv &= finite(velocity[2])
            result.append(TrajectoryRecord(
                timestamp=timestamp, x_m=position[0], y_m=position[1], z_m=position[2],
                vx_m_s=velocity[0], vy_m_s=velocity[1], vz_m_s=velocity[2],
                position_valid=hp and vp, horizontal_position_valid=hp, vertical_position_valid=vp,
                velocity_valid=hv and vv, horizontal_velocity_valid=hv, vertical_velocity_valid=vv,
                position_source='native', velocity_source='native', position_reset_counter=reset,
                vertical_reset_counter=reset, source_platform=self.platform_name,
                raw={**raw(record), 'native_frame': 'NED', 'ekf_core': core,
                     'solution_status': solution, 'status_timestamp': status_time},
            ))
        return result

    def extract_telemetry(self):
        result = []
        for record in self._iter_records():
            if record['name'] != 'RAD':
                continue
            values = fields(record)
            timestamp = self._timestamp(values)
            if timestamp is None:
                continue
            result.append(TelemetryRecord(
                timestamp=timestamp, rssi_raw=values.get('RSSI'), remote_rssi_raw=values.get('RemRSSI'),
                noise_raw=values.get('Noise'), remote_noise_raw=values.get('RemNoise'),
                tx_buffer_percent=values.get('TxBuf'), rx_error_count=values.get('RxErrors'),
                corrected_packet_count=values.get('Fixed'), source_platform=self.platform_name, raw=raw(record),
            ))
        return result

    def extract_failsafe(self):
        result = []
        # AP_Logger LogErrorSubsystem and LogErrorCode; unknown codes remain ERR events.
        mapping = {5: ('FAILSAFE_RADIO', 'manual_control_signal_lost'),
                   6: ('FAILSAFE_BATT', 'battery_warning'), 8: ('FAILSAFE_GCS', 'gcs_connection_lost'),
                   9: ('FAILSAFE_FENCE', 'geofence_breached'), 17: ('FAILSAFE_EKFINAV', 'navigator_failure'),
                   23: ('FAILSAFE_TERRAIN', None), 26: ('FAILSAFE_SENSORS', None),
                   31: ('FAILSAFE_DEADRECKON', None)}
        for record in self._iter_records():
            values = fields(record)
            timestamp = self._timestamp(values)
            if record['name'] == 'ERR' and timestamp is not None:
                reason, field = mapping.get(values.get('Subsys'), (None, None))
                code = values.get('ECode')
                if reason and code in (0, 1):
                    specific = {field: int(code) if field == 'battery_warning' else bool(code)} if field else {}
                    result.append(FailsafeRecord(timestamp=timestamp, source_platform=self.platform_name,
                                                 failsafe_active=bool(code), reason=reason,
                                                 raw=raw(record), **specific))
            elif record['name'] in {'XKF4', 'NKF4'} and timestamp is not None and values.get('SS') is not None:
                solution = values['SS']
                result.append(FailsafeRecord(
                    timestamp=timestamp, attitude_invalid=not bool(solution & 1),
                    local_position_invalid=not bool(solution & (8 | 16)),
                    global_position_invalid=not bool(solution & 16), local_altitude_invalid=not bool(solution & 32),
                    local_velocity_invalid=not bool(solution & 2 and solution & 4),
                    source_platform=self.platform_name, raw=raw(record),
                ))
            elif record['name'] in {'BAT', 'BAT2', 'BAT3', 'BAT4'} and timestamp is not None and values.get('H') in (0, 1):
                result.append(FailsafeRecord(timestamp=timestamp, battery_unhealthy=not bool(values['H']),
                                             source_platform=self.platform_name, raw=raw(record)))
        return result

    def extract_cell_battery(self):
        result = []
        for record in self._iter_records():
            if record['name'] != 'BCL':
                continue
            values = fields(record)
            timestamp = self._timestamp(values)
            formats = dict(zip(record['labels'], record['format']))
            cells = [values[key] / 1000.0 if formats[key] == 'H' else values[key]
                     for key in sorted(values, key=lambda key: (len(key), key))
                     if key.startswith('V') and key[1:].isdigit() and finite(values[key])
                     and values[key] > 0 and values[key] != 65535]
            if timestamp is not None and cells:
                result.append(BatteryRecord(timestamp=timestamp, voltage_v=values.get('Volt'),
                                             cell_count=len(cells), cell_voltages_v=cells,
                                             max_cell_voltage_delta_v=max(cells)-min(cells),
                                             source_platform=self.platform_name, raw=raw(record)))
        return result

    def extract_additional_data(self):
        inventory, groups = {}, defaultdict(list)
        for record in self._iter_records():
            item = inventory.setdefault(record['name'], {'record_count': 0, 'fields': set()})
            item['record_count'] += 1
            item['fields'].update(record['labels'])
            if record['name'] != 'FMT':
                groups[record['name']].append(raw(record))
        for item in inventory.values():
            item['fields'] = sorted(item['fields'])
        return {'message_inventory': inventory, 'source_record_groups': dict(groups),
                'dataflash_schemas': list(self._schemas.values()),
                'schema_history': self._schema_history, 'decode_stats': self._decode_stats}
