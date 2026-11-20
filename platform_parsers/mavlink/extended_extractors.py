"""Shared MAVLink evidence extensions used by both TLOG adapters."""
from collections import Counter, defaultdict
import math

from platform_parsers.common.evidence_model import GPSRecord, ParameterRecord, TrajectoryRecord, FailsafeRecord, BatteryRecord
from platform_parsers.common.extraction import json_value


def mavlink_decoder(stream=None):
    # A v2 dialect also decodes v1 frames. The default mavutil dialect may
    # omit ODOMETRY/PARAM_EXT and other message IDs above 255.
    from pymavlink.dialects.v20 import ardupilotmega
    return ardupilotmega.MAVLink(stream)


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def sender(message):
    return (message.get_srcSystem() if hasattr(message, 'get_srcSystem') else 0,
            message.get_srcComponent() if hasattr(message, 'get_srcComponent') else 0)


def raw_record(record):
    message = record['message']
    system, component = sender(message)
    return {'message_type': message.get_type(), 'timestamp': record['timestamp'],
            'timestamp_us': record.get('timestamp_us'), 'packet_offset': record.get('packet_offset'),
            'mavlink_version': record.get('mavlink_version'), 'source_system': system,
            'source_component': component, 'message': json_value(message.to_dict())}


def extra_gps(records, platform):
    result = []
    for record in records:
        message = record['message']
        if message.get_type() != 'GPS2_RAW':
            continue
        def scaled(name, divisor, sentinel=None):
            value = getattr(message, name, None)
            return None if value is None or value == sentinel else value / divisor
        result.append(GPSRecord(
            timestamp=record['timestamp'], latitude=scaled('lat', 1e7), longitude=scaled('lon', 1e7),
            altitude_m=scaled('alt', 1000), speed_m_s=scaled('vel', 100, 65535),
            satellites=getattr(message, 'satellites_visible', None), fix_type=getattr(message, 'fix_type', None),
            hdop=scaled('eph', 100, 65535), vdop=scaled('epv', 100, 65535),
            heading_deg=scaled('cog', 100, 65535), source_platform=platform, raw=raw_record(record),
        ))
    return result


def extra_parameters(records, platform):
    result = []
    for record in records:
        message = record['message']
        if message.get_type() not in {'PARAM_EXT_VALUE', 'PARAM_EXT_SET'}:
            continue
        name = getattr(message, 'param_id', '')
        value = getattr(message, 'param_value', '')
        if isinstance(name, bytes):
            name = name.decode('utf-8', errors='replace')
        if isinstance(value, bytes):
            value = value.decode('utf-8', errors='replace')
        result.append(ParameterRecord(record['timestamp'], str(name).rstrip('\0'), str(value).rstrip('\0'),
                                      source_platform=platform, raw=raw_record(record)))
    return result


def extra_battery(records, platform):
    """SYS_STATUS carries battery measurements even without BATTERY_STATUS."""
    result = []
    for record in records:
        message = record['message']
        if message.get_type() != 'SYS_STATUS':
            continue
        voltage = getattr(message, 'voltage_battery', None)
        current = getattr(message, 'current_battery', None)
        remaining = getattr(message, 'battery_remaining', None)
        voltage = voltage / 1000.0 if voltage not in (None, 65535) else None
        current = current / 100.0 if current not in (None, -1) else None
        remaining = remaining / 100.0 if remaining is not None and 0 <= remaining <= 100 else None
        if any(value is not None for value in (voltage, current, remaining)):
            result.append(BatteryRecord(timestamp=record['timestamp'], voltage_v=voltage,
                                         current_a=current, remaining=remaining,
                                         source_platform=platform, raw=raw_record(record)))
    return result


TRAJECTORY_MESSAGES = ('LOCAL_POSITION_NED', 'LOCAL_POSITION_NED_COV', 'ODOMETRY')


def primary_trajectory_channel(records):
    counts = Counter((record['message'].get_type(), *sender(record['message'])) for record in records
                     if record['message'].get_type() in TRAJECTORY_MESSAGES
                     and (record['message'].get_type() != 'ODOMETRY'
                          or getattr(record['message'], 'frame_id', None) in (1, 4)))
    return (min(counts, key=lambda key: (-counts[key], TRAJECTORY_MESSAGES.index(key[0]), key[1:]))
            if counts else None)


def extract_trajectory(records, platform):
    records = list(records)
    primary = primary_trajectory_channel(records)
    statuses, result, segment, last_boot = {}, [], 0, None
    for record in records:
        message = record['message']
        kind = message.get_type()
        identity = sender(message)
        if kind in {'ESTIMATOR_STATUS', 'EKF_STATUS_REPORT'}:
            statuses[identity] = (getattr(message, 'flags', None), record['timestamp'])
        if (kind, *identity) != primary:
            continue
        position = [number(getattr(message, axis, None)) for axis in ('x', 'y', 'z')]
        velocity = [number(getattr(message, axis, None)) for axis in ('vx', 'vy', 'vz')]
        acceleration = [number(getattr(message, axis, None)) for axis in ('ax', 'ay', 'az')]
        frame = getattr(message, 'frame_id', 1)  # LOCAL_POSITION_NED is NED by contract
        if frame not in (1, 4):
            continue  # Unaligned local frames are preserved in additional_data.
        if kind == 'ODOMETRY':
            child = getattr(message, 'child_frame_id', None)
            if child == 12 and all(value is not None for value in velocity):  # BODY_FRD
                q = getattr(message, 'q', [])
                if len(q) != 4 or any(number(value) is None for value in q) or abs(sum(v*v for v in q)-1) > .01:
                    velocity = [None] * 3
                else:
                    w, x, y, z = q
                    a, b, c = velocity
                    velocity = [(1-2*(y*y+z*z))*a + 2*(x*y-z*w)*b + 2*(x*z+y*w)*c,
                                2*(x*y+z*w)*a + (1-2*(x*x+z*z))*b + 2*(y*z-x*w)*c,
                                2*(x*z-y*w)*a + 2*(y*z+x*w)*b + (1-2*(x*x+y*y))*c]
            elif child != frame:
                velocity = [None] * 3
        def enu(values):
            if frame == 4:
                return values
            return [values[1], values[0], -values[2] if values[2] is not None else None]
        position, velocity, acceleration = enu(position), enu(velocity), enu(acceleration)
        boot = getattr(message, 'time_boot_ms', getattr(message, 'time_usec', None))
        if last_boot is not None and boot is not None and boot < last_boot:
            segment += 1
        last_boot = boot
        reset = getattr(message, 'reset_counter', segment)
        flags, flag_time = statuses.get(identity, (None, None))
        hp = all(value is not None for value in position[:2]) and (flags is None or bool(flags & (8 | 16)))
        vp = position[2] is not None and (flags is None or bool(flags & (32 | 64)))
        hv = all(value is not None for value in velocity[:2]) and (flags is None or bool(flags & 2))
        vv = velocity[2] is not None and (flags is None or bool(flags & 4))
        quality = getattr(message, 'quality', None)
        if quality == -1:
            hp = vp = hv = vv = False
        result.append(TrajectoryRecord(
            timestamp=record['timestamp'], x_m=position[0], y_m=position[1], z_m=position[2],
            vx_m_s=velocity[0], vy_m_s=velocity[1], vz_m_s=velocity[2],
            ax_m_s2=acceleration[0], ay_m_s2=acceleration[1], az_m_s2=acceleration[2],
            position_valid=hp and vp, horizontal_position_valid=hp, vertical_position_valid=vp,
            velocity_valid=hv and vv, horizontal_velocity_valid=hv, vertical_velocity_valid=vv,
            acceleration_valid=all(value is not None for value in acceleration),
            position_source='native', velocity_source='native',
            acceleration_source='native' if kind == 'LOCAL_POSITION_NED_COV' else 'unavailable',
            position_reset_counter=reset, vertical_reset_counter=reset, source_platform=platform,
            raw={**raw_record(record), 'native_frame': frame, 'estimator_flags': flags,
                 'estimator_status_timestamp': flag_time, 'source_boot_time': boot},
        ))
    return result


def structured_failsafe(records, platform):
    from pymavlink.dialects.v20 import common as m
    result = []
    for record in records:
        message = record['message']
        kind, values = message.get_type(), {}
        if kind in {'ESTIMATOR_STATUS', 'EKF_STATUS_REPORT'}:
            flags = getattr(message, 'flags', None)
            if flags is not None:
                values = {'attitude_invalid': not bool(flags & 1),
                          'local_velocity_invalid': not bool(flags & 2 and flags & 4),
                          'local_position_invalid': not bool(flags & (8 | 16)),
                          'global_position_invalid': not bool(flags & 16),
                          'local_altitude_invalid': not bool(flags & (32 | 64))}
        elif kind == 'FENCE_STATUS':
            status = getattr(message, 'breach_status', None)
            if status is not None:
                values['geofence_breached'] = status != 0
        elif kind == 'SYS_STATUS':
            enabled = getattr(message, 'onboard_control_sensors_enabled', 0)
            present = getattr(message, 'onboard_control_sensors_present', 0)
            healthy = getattr(message, 'onboard_control_sensors_health', 0)
            for bit, field in ((m.MAV_SYS_STATUS_SENSOR_3D_GYRO, 'angular_velocity_invalid'),
                               (m.MAV_SYS_STATUS_SENSOR_BATTERY, 'battery_unhealthy')):
                if present & enabled & bit:
                    values[field] = not bool(healthy & bit)
        elif kind == 'HEARTBEAT' and getattr(message, 'system_status', None) in (5, 6):
            values['critical_failure'] = True
        if values:
            result.append(FailsafeRecord(timestamp=record['timestamp'], source_platform=platform,
                                         raw=raw_record(record), **values))
    return result


def additional_data(records):
    records = list(records)
    inventory, groups = {}, defaultdict(list)
    # Preserve every decoded packet, including observations collapsed into
    # normalized state changes and messages with no scalar schema mapping.
    for record in records:
        kind = record['message'].get_type()
        item = inventory.setdefault(kind, {'record_count': 0, 'fields': set()})
        item['record_count'] += 1
        item['fields'].update(record['message'].to_dict())
        groups[kind].append(raw_record(record))
    for item in inventory.values():
        item['fields'] = sorted(item['fields'])
    primary = primary_trajectory_channel(records)
    return {'message_inventory': inventory, 'source_record_groups': dict(groups),
            'trajectory_selection': {'channel': list(primary) if primary else None,
                                     'rule': 'Most observations for one message/system/component channel; alternatives remain in source_record_groups.'}}
