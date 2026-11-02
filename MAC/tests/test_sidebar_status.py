import dataclasses
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calibration_status import CalibrationHold, CalibrationStatus, CALIBRATION_KEYS
from telemetry import AirTelemetry, VALIDITY_FLAGS, STATE_FLAGS


def packet(**changes):
    fields = {field.name: 0 for field in dataclasses.fields(AirTelemetry)}
    fields.update(sequence=1, timestamp_ms=50,
                  validity_flags=(1 << VALIDITY_FLAGS['fc_telemetry']) |
                                 (1 << VALIDITY_FLAGS['inav_status']) |
                                 (1 << VALIDITY_FLAGS['rc_check']),
                  state_flags=sum(1 << STATE_FLAGS[name] for name in
                                  ('ground_link_valid', 'keyboard_packet_valid',
                                   'left_glove_valid', 'left_imu_valid', 'right_imu_valid')))
    fields.update(changes)
    return AirTelemetry(**fields)


def calibrated(data, **changes):
    return dataclasses.replace(data,
        validity_flags=data.validity_flags | (1 << VALIDITY_FLAGS['flex_calibration']),
        state_flags=data.state_flags | (1 << STATE_FLAGS['glove_orientation_calibrated']),
        **changes)


class SidebarStatusTests(unittest.TestCase):
    def test_all_channel_counts_recover_from_actual_firmware_rounding(self):
        for matched, percent in enumerate((0, 13, 25, 38, 50, 63, 75, 88, 100)):
            self.assertEqual(packet(rc_accuracy_percent=percent).rc_channel_agreement,
                             (matched, 8))
        self.assertIsNone(packet(rc_accuracy_percent=95).rc_channel_agreement)
        self.assertIsNone(packet(validity_flags=0, rc_accuracy_percent=100).rc_channel_agreement)
        self.assertIsNone(packet(validity_flags=1 << VALIDITY_FLAGS['rc_check'],
                                 rc_accuracy_percent=100).rc_channel_agreement)

    def test_mac_passes_chord_to_right_without_a_second_hold_gate(self):
        hold = CalibrationHold()
        other_keys = (1 << 0) | (1 << 14)
        self.assertEqual(hold.filter(CALIBRATION_KEYS | other_keys, now=0), CALIBRATION_KEYS | other_keys)
        self.assertEqual(hold.filter(CALIBRATION_KEYS, now=2.99), CALIBRATION_KEYS)
        self.assertEqual(hold.filter(CALIBRATION_KEYS, now=3), CALIBRATION_KEYS)
        self.assertEqual(hold.filter(1 << 11, now=3.1), 1 << 11)
        self.assertEqual(hold.filter(CALIBRATION_KEYS, now=3.2), CALIBRATION_KEYS)
        self.assertEqual(hold.filter(0, now=5), 0)
        self.assertEqual(hold.filter(CALIBRATION_KEYS, now=6), CALIBRATION_KEYS)

    def test_completion_requires_both_telemetry_signals_and_live_sources(self):
        status = CalibrationStatus()
        data = packet()
        self.assertEqual(status.update(data, 0, True), 'NOT CALIBRATED')
        self.assertEqual(status.update(calibrated(data), 0, True), 'CALIBRATED')
        self.assertEqual(status.update(None, 0, True), 'UNAVAILABLE')
        self.assertEqual(status.update(calibrated(data), 0, False), 'UNAVAILABLE')
        for name in ('ground_link_valid', 'left_glove_valid', 'left_imu_valid', 'right_imu_valid'):
            missing = dataclasses.replace(calibrated(data),
                state_flags=calibrated(data).state_flags & ~(1 << STATE_FLAGS[name]))
            self.assertEqual(status.update(missing, 0, True), 'UNAVAILABLE')
        orientation_only = dataclasses.replace(calibrated(data), validity_flags=data.validity_flags)
        self.assertEqual(status.update(orientation_only, 0, True), 'NOT CALIBRATED')

    def test_request_can_complete_only_after_new_telemetry(self):
        status = CalibrationStatus()
        data = calibrated(packet())
        self.assertEqual(status.update(data, CALIBRATION_KEYS, True, now=0), 'CALIBRATED')
        self.assertEqual(status.update(data, CALIBRATION_KEYS, True, now=3), 'CALIBRATING')
        self.assertEqual(status.update(data, 0, True, now=4), 'CALIBRATING')
        self.assertEqual(status.update(packet(sequence=2), 0, True, now=5), 'CALIBRATING')
        self.assertEqual(status.update(calibrated(packet(sequence=3)), 0, True, now=19), 'CALIBRATED')

    def test_timeout_never_marks_success_and_stale_clears_progress(self):
        status = CalibrationStatus()
        data = calibrated(packet())
        status.update(data, CALIBRATION_KEYS, True, now=0)
        status.update(data, CALIBRATION_KEYS, True, now=3)
        self.assertEqual(status.update(data, 0, True, now=20), 'UNAVAILABLE')
        self.assertEqual(status.update(data, 0, True, now=21), 'UNAVAILABLE')
        self.assertEqual(status.update(None, 0, True, now=22), 'UNAVAILABLE')
        self.assertEqual(status.update(packet(), 0, True, now=23), 'NOT CALIBRATED')


if __name__ == '__main__':
    unittest.main()
