"""Wire-level regression tests for cross-platform extraction parity."""
import json
from pathlib import Path
import struct

import pytest

from platform_parsers.ardupilot.dataflash_parser import ArduPilotDataFlashParser
from platform_parsers.ardupilot.tlog_parser import ArduPilotTLogParser
from platform_parsers.betaflight.blackbox_parser import BetaflightBlackboxParser
from platform_parsers.inav.blackbox_parser import INAVBlackboxParser
from platform_parsers.emuflight.blackbox_parser import EmuFlightBlackboxParser
from platform_parsers.mavlink.tlog_parser import MAVLinkTLogParser
from reporting.normalized_report import NormalizedForensicReport


def dataflash_bytes():
    schemas = [
        ('XKF4', 'QBI', 'TimeUS,C,SS'),
        ('XKF1', 'QBffffff', 'TimeUS,C,PN,PE,PD,VN,VE,VD'),
        ('RAD', 'QBBBBHHB', 'TimeUS,RSSI,RemRSSI,Noise,RemNoise,RxErrors,Fixed,TxBuf'),
        ('ERR', 'QBB', 'TimeUS,Subsys,ECode'),
        ('BCL', 'QBfHHH', 'TimeUS,Instance,Volt,V1,V2,V3'),
        ('BAT', 'QfB', 'TimeUS,Volt,RemPct'),
        ('IMU', 'Qfff', 'TimeUS,AccX,AccY,AccZ'),
        ('RCOU', 'QHH', 'TimeUS,C1,C2'),
    ]
    data, definitions = bytearray(), {}
    for message_type, (name, fmt, labels) in enumerate(schemas, 150):
        length = 3 + struct.calcsize('<' + fmt)
        data += b'\xa3\x95\x80' + struct.pack('<BB4s16s64s', message_type, length, name.encode(), fmt.encode(), labels.encode())
        definitions[name] = (message_type, fmt)
    def append(name, *values):
        message_type, fmt = definitions[name]
        data.extend(b'\xa3\x95' + bytes([message_type]) + struct.pack('<' + fmt, *values))
    append('XKF4', 0, 0, 63)
    append('XKF1', 100000, 0, 10, 20, -3, 1, 2, -.5)
    append('XKF1', 200000, 0, 10.1, 20.2, -3.05, 1, 2, -.5)
    append('XKF4', 300000, 0, 1)
    append('XKF1', 400000, 0, 10.4, 20.8, -3.2, 1, 2, -.5)
    append('RAD', 500000, 100, 90, 5, 6, 3, 2, 77)
    append('ERR', 600000, 5, 1)
    append('ERR', 700000, 5, 0)
    append('BCL', 800000, 0, 8.1, 4000, 4100, 65535)
    append('BAT', 900000, 8.1, 1)
    append('IMU', 1000000, .1, .2, -9.8)
    append('RCOU', 1000000, 1200, 1300)
    return bytes(data)


def test_dataflash_native_trajectory_health_radio_cells_and_raw_groups(tmp_path):
    path = tmp_path / 'extended.bin'
    path.write_bytes(dataflash_bytes())
    parser = ArduPilotDataFlashParser(path)
    assert parser.identify(path)['supported']
    evidence = parser.parse()
    assert len(evidence.trajectory) == 3
    first = evidence.trajectory[0]
    assert (first.x_m, first.y_m, first.z_m) == (20, 10, 3)
    assert (first.vx_m_s, first.vy_m_s, first.vz_m_s) == (2, 1, .5)
    assert first.position_valid and first.velocity_valid
    assert not evidence.trajectory[-1].position_valid
    assert first.raw['raw_fields']['PN'] == 10
    offset = first.raw['file_offset']
    assert path.read_bytes()[offset:offset + 2] == b'\xa3\x95'
    link = evidence.telemetry[0]
    assert (link.rssi_raw, link.remote_rssi_raw, link.rx_error_count, link.tx_buffer_percent) == (100, 90, 3, 77)
    assert link.tx_buffer_overruns is None
    transitions = [record.manual_control_signal_lost for record in evidence.failsafe
                   if record.manual_control_signal_lost is not None]
    assert transitions == [True, False]
    cells = next(record for record in evidence.battery if record.cell_voltages_v)
    assert cells.cell_count == 2
    assert cells.cell_voltages_v == [4., 4.1]
    assert cells.max_cell_voltage_delta_v == pytest.approx(.1)
    bat = next(record for record in evidence.battery if record.raw['dataset'] == 'BAT')
    assert bat.remaining == .01
    groups = evidence.additional_data['source_record_groups']
    assert groups['IMU'][0]['raw_fields']['AccZ'] == pytest.approx(-9.8)
    assert groups['RCOU'][0]['fields']['C1'] == 1200
    assert list(parser._iter_records()) == list(parser._iter_records())
    report = NormalizedForensicReport(evidence).build()
    assert report['record_counts']['trajectory'] == 3
    assert report['extraction_coverage']['telemetry']['status'] == 'extracted'
    assert report['provenance']['normalized_records']['trajectory'][0]['x_m'] == 20
    output = tmp_path / 'report.json'
    NormalizedForensicReport(evidence).save(output)
    assert json.loads(output.read_text())['additional_data']['source_record_groups']['IMU']
    assert Path(str(output) + '.sha256').exists()


def tlog_bytes(messages):
    from pymavlink.dialects.v20 import ardupilotmega as m
    mav = m.MAVLink(None, srcSystem=1, srcComponent=1)
    data = bytearray()
    for index, message in enumerate(messages):
        mav.seq = index % 256
        data += struct.pack('>Q', 1700000000000000 + index * 100000) + message.pack(mav)
    return bytes(data)


def rich_messages():
    from pymavlink.dialects.v20 import ardupilotmega as m
    return [
        m.MAVLink_heartbeat_message(2, 3, 128, 0, 4, 3),
        m.MAVLink_estimator_status_message(1, 63, 0., 0., 0., 0., 0., 0., .1, .2),
        m.MAVLink_local_position_ned_message(100, 10., 20., -3., 1., 2., -.5),
        m.MAVLink_local_position_ned_message(200, 10.1, 20.2, -3.05, 1., 2., -.5),
        m.MAVLink_radio_status_message(100, 90, 77, 5, 6, 3, 2),
        m.MAVLink_sys_status_message(1, 1, 1, 100, 12000, 250, 80, 100, 4, 0, 0, 0, 0),
        m.MAVLink_fence_status_message(1, 1, 1, 0),
        m.MAVLink_param_ext_value_message(b'GAIN', b'1.25', 9, 1, 0),
        m.MAVLink_attitude_message(200, .1, .2, .3, .01, .02, .03),
        m.MAVLink_gps2_raw_message(100, 3, 473979450, 85461760, 230000, 65535, 150, 500, 9000, 10, 0, 0),
    ]


@pytest.mark.parametrize('parser_class', [MAVLinkTLogParser, ArduPilotTLogParser])
def test_both_tlog_parsers_extract_extended_messages(parser_class, tmp_path):
    path = tmp_path / 'extended.tlog'
    path.write_bytes(tlog_bytes(rich_messages()))
    parser = parser_class(path)
    evidence = parser.parse()
    assert len(evidence.trajectory) == 2
    first = evidence.trajectory[0]
    assert (first.x_m, first.y_m, first.z_m) == (20, 10, 3)
    assert first.position_valid and first.velocity_valid
    assert first.timestamp == 1700000000.2
    assert evidence.gps[0].altitude_m == 230
    assert evidence.gps[0].hdop is None
    assert evidence.gps[0].vdop == 1.5
    assert any(record.name == 'GAIN' and record.value == '1.25' for record in evidence.parameters)
    radio = next(record for record in evidence.telemetry if record.rssi_raw is not None)
    assert radio.tx_buffer_percent == 77 and radio.rx_error_count == 3
    assert radio.tx_buffer_overruns is None and radio.rx_message_lost_count is None
    status = next(record for record in evidence.telemetry if record.communication_error_count is not None)
    assert status.rx_message_lost_rate == .01
    assert status.communication_error_count == 4
    battery = next(record for record in evidence.battery if record.raw['message_type'] == 'SYS_STATUS')
    assert (battery.voltage_v, battery.current_a, battery.remaining) == (12., 2.5, .8)
    assert any(record.geofence_breached is True for record in evidence.failsafe)
    groups = evidence.additional_data['source_record_groups']
    assert groups['ATTITUDE'][0]['message']['roll'] == pytest.approx(.1)
    assert sum(len(group) for group in groups.values()) == len(rich_messages())
    assert groups['HEARTBEAT'][0]['source_system'] == 1
    assert evidence.metadata.start_time == 1700000000.
    assert evidence.metadata.duration == pytest.approx(.9)
    report = NormalizedForensicReport(evidence).build()
    assert report['record_counts']['trajectory'] == 2
    assert report['extraction_coverage']['trajectory']['populated_fields']['x_m'] == 2


def odometry(frame=1, child=12, quality=100):
    from pymavlink.dialects.v20 import ardupilotmega as m
    return m.MAVLink_odometry_message(100, frame, child, 10, 20, -3, [1., 0., 0., 0.],
                                     1, 2, -.5, 0, 0, 0, [0.] * 21, [0.] * 21,
                                     reset_counter=2, quality=quality)


def test_odometry_v2_frame_and_velocity_conversion(tmp_path):
    path = tmp_path / 'odom.tlog'
    path.write_bytes(tlog_bytes([odometry()]))
    evidence = MAVLinkTLogParser(path).parse()
    assert len(evidence.trajectory) == 1
    record = evidence.trajectory[0]
    assert (record.x_m, record.y_m, record.z_m) == (20, 10, 3)
    assert (record.vx_m_s, record.vy_m_s, record.vz_m_s) == (2, 1, .5)
    assert record.position_reset_counter == 2
    path.write_bytes(tlog_bytes([odometry(frame=20)]))
    evidence = MAVLinkTLogParser(path).parse()
    assert evidence.trajectory == []
    assert evidence.additional_data['source_record_groups']['ODOMETRY']
    path.write_bytes(tlog_bytes([odometry(quality=-1)]))
    assert not MAVLinkTLogParser(path).parse().trajectory[0].position_valid


def uvb(value):
    data = bytearray()
    while value >= 128:
        data.append((value & 127) | 128)
        value >>= 7
    return bytes(data) + bytes([value])


def svb(value):
    return uvb((value << 1) ^ (value >> 31))


def blackbox_bytes(firmware):
    is_inav = firmware.startswith('INAV')
    names = ['loopIteration', 'time', 'gyroADC[0]', 'accADC[2]', 'motor[0]', 'rssi']
    names += ['vbat', 'amperage', 'navPos[0]', 'navPos[1]', 'navPos[2]',
              'navVel[0]', 'navVel[1]', 'navVel[2]', 'navFlags'] if is_inav else ['vbatLatest', 'amperageLatest']
    first = [0, 1000000, 10, 2048, 1100, 900]
    first += [1200, 250, 1000, 2000, 300, 100, 200, 50, 5] if is_inav else [1818, 250]
    second = first.copy()
    second[0], second[1], second[2], second[5], second[6] = 1, 1100000, 11, 901, first[6] - 10
    if is_inav:
        second[8:11] = [1010, 2020, 305]
    n = len(names)
    headers = [
        'H Product:Blackbox flight data recorder by Nicholas Sherlock', 'H Data version:2',
        f'H Firmware type:{firmware.split()[0]}', f'H Firmware revision:{firmware}',
        'H I interval:32', 'H P interval:1/1', 'H vbatref:1838', 'H vbatscale:110',
        'H vbat_divider:10', 'H vbat_multiplier:1', 'H currentMeter:0,806',
        'H Field I name:' + ','.join(names), 'H Field I signed:' + ','.join(['1'] * n),
        'H Field I predictor:' + ','.join(['0'] * n), 'H Field I encoding:' + ','.join(['0'] * n),
        'H Field P predictor:' + ','.join(['6', '2'] + ['1'] * (n - 2)),
        'H Field P encoding:' + ','.join(['9'] + ['0'] * (n - 1)),
        'H Field S name:flightModeFlags,stateFlags,failsafePhase,rxSignalReceived,rxFlightChannelsValid',
        'H Field S signed:0,0,0,0,0', 'H Field S predictor:0,0,0,0,0', 'H Field S encoding:1,1,1,1,1',
    ]
    data = ('\n'.join(headers) + '\n').encode()
    data += b'I' + b''.join(svb(value) for value in first)
    data += b'S' + b''.join(uvb(value) for value in [1, 0, 0, 1, 1])
    data += b'P' + b''.join(svb(second[i] - first[i]) for i in range(1, n))
    data += b'S' + b''.join(uvb(value) for value in [1, 0, 1, 0, 0])
    data += b'E' + bytes([15]) + uvb(3) + b'E\xffEnd of log\0'
    return data


@pytest.mark.parametrize('parser_class,firmware', [
    (BetaflightBlackboxParser, 'Betaflight 4.5.0'),
    (INAVBlackboxParser, 'INAV 7.1.0'),
    (EmuFlightBlackboxParser, 'EmuFlight 0.4.0'),
])
def test_blackbox_all_frame_types_preserve_sensor_control_and_status_data(parser_class, firmware, tmp_path):
    path = tmp_path / 'extended.bbl'
    path.write_bytes(blackbox_bytes(firmware))
    parser = parser_class(path)
    assert parser.identify(path)['supported']
    evidence = parser.parse()
    assert evidence.parameters
    assert len(evidence.states) == 3
    assert any(record.manual_control_signal_lost is True for record in evidence.failsafe)
    assert [record.rc_signal_strength_raw for record in evidence.telemetry] == [900, 901]
    assert [event.event_type for event in evidence.events] == ['DISARM', 'LOG_END']
    groups = evidence.additional_data['source_record_groups']
    assert [record['gyroADC[0]'] for record in groups['main_frames']] == [10, 11]
    assert [record['frame_type'] for record in groups['main_frames']] == ['I', 'P']
    assert groups['main_frames'][0]['motor[0]'] == 1100
    assert all(path.read_bytes()[record['file_offset']] in (ord('I'), ord('P')) for record in groups['main_frames'])
    if firmware.startswith('INAV'):
        assert len(evidence.trajectory) == 2
        first = evidence.trajectory[0]
        assert (first.x_m, first.y_m, first.z_m) == (20, 10, 3)
        assert (first.vx_m_s, first.vy_m_s, first.vz_m_s) == (2, 1, .5)
        assert first.position_valid and first.velocity_valid
        assert evidence.battery[0].voltage_v == 12
        assert evidence.battery[0].current_a == 2.5
    elif firmware.startswith('Betaflight'):
        assert len(evidence.battery) == 2
        assert evidence.trajectory == []  # Body IMU data is not local position.
    else:
        assert evidence.battery == []  # Unverified units retained in raw groups.
    output = tmp_path / 'report.json'
    NormalizedForensicReport(evidence).save(output)
    report = json.loads(output.read_text())
    assert report['extraction_coverage']['events']['record_count'] == 2
    assert report['extraction_coverage']['commands']['status'] == 'unsupported'
    assert report['additional_data']['source_record_groups']['main_frames'][1]['gyroADC[0]'] == 11


def test_blackbox_logs_keep_sessions_and_diagnostics_separate(tmp_path):
    path = tmp_path / 'sessions.bbl'
    path.write_bytes(blackbox_bytes('INAV 7.1.0') * 2)
    evidence = INAVBlackboxParser(path).parse()
    assert [record.vertical_reset_counter for record in evidence.trajectory] == [0, 0, 1, 1]
    assert len(evidence.additional_data['blackbox_logs']) == 2
    damaged = blackbox_bytes('INAV 7.1.0').replace(b'H Field I encoding:0,', b'H Field I encoding:99,', 1)
    path.write_bytes(damaged)
    evidence = INAVBlackboxParser(path).parse()
    stats = evidence.additional_data['blackbox_logs'][0]['decode_stats']
    assert stats['frames_corrupt']['I'] > 0
    assert 'unsupported encoding' in stats['decode_error_samples'][0]['reason']


def test_dataflash_replays_schema_changes_in_source_order(tmp_path):
    def fmt(format, labels):
        return b'\xa3\x95\x80' + struct.pack('<BB4s16s64s', 150, 3 + struct.calcsize('<' + format),
                                            b'IMU', format.encode(), labels.encode())
    data = fmt('Qf', 'TimeUS,AccX') + b'\xa3\x95\x96' + struct.pack('<Qf', 100, 1.25)
    data += fmt('Qff', 'TimeUS,AccX,AccY') + b'\xa3\x95\x96' + struct.pack('<Qff', 200, 2.5, 3.5)
    path = tmp_path / 'schema_changes.bin'
    path.write_bytes(data)
    evidence = ArduPilotDataFlashParser(path).parse()
    frames = evidence.additional_data['source_record_groups']['IMU']
    assert len(frames) == 2
    assert frames[0]['raw_fields'] == {'TimeUS': 100, 'AccX': 1.25}
    assert frames[1]['raw_fields'] == {'TimeUS': 200, 'AccX': 2.5, 'AccY': 3.5}
    assert len(evidence.additional_data['schema_history']) == 2
    assert evidence.additional_data['decode_stats']['decoded_records'] == 2


def test_dataflash_truncation_and_invalid_schemas_are_reported(tmp_path):
    path = tmp_path / 'partial.bin'
    path.write_bytes(dataflash_bytes()[:-1])
    evidence = ArduPilotDataFlashParser(path).parse()
    assert evidence.additional_data['decode_stats']['truncated_at_end']
    assert evidence.additional_data['extraction_coverage']['gps']['decoder_incomplete']
    bad_fmt = b'\xa3\x95\x80' + struct.pack('<BB4s16s64s', 151, 100, b'IMU', b'Qf', b'TimeUS,AccX')
    path.write_bytes(bad_fmt)
    evidence = ArduPilotDataFlashParser(path).parse()
    assert evidence.additional_data['decode_stats']['errors']
    assert evidence.additional_data['extraction_coverage']['gps']['status'] == 'decode_incomplete'
