import dataclasses
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calibration_guide import (CalibrationGuide, CalibrationTransmission,
                               CalibrationTransmissionObserver)
from calibration_status import CalibrationHold, CalibrationStatus, CALIBRATION_KEYS
from test_sidebar_status import packet, calibrated


class CalibrationGuideTests(unittest.TestCase):
    def setUp(self):
        self.guide = CalibrationGuide()
        self.tx = CalibrationTransmission(0, 1, 3)

    def update(self, now, data=None, keys=0, usb=True, tx=None):
        self.guide.update(packet(sequence=int(now * 20)) if data is None else data,
                          usb, keys, self.tx if tx is None else tx, now=now)
        return self.guide.frame(now)

    def test_hold_does_not_start_guide_until_successful_transmission(self):
        pending = CalibrationTransmission(0)
        frame = self.update(0, keys=CALIBRATION_KEYS, tx=pending)
        self.assertEqual((frame.phase, frame.remaining), ('hold', 3))
        self.assertEqual(self.update(1.01, keys=CALIBRATION_KEYS, tx=pending).remaining, 2)
        self.assertEqual(self.update(3.05, keys=CALIBRATION_KEYS, tx=pending).phase, 'hold')
        self.assertEqual(self.update(3.08, keys=CALIBRATION_KEYS).phase, 'stage')
        self.assertAlmostEqual(self.guide.frame(3.08).progress, .08 / 5)

    def test_early_release_cancels_only_hold(self):
        pending = CalibrationTransmission(0)
        self.update(0, keys=CALIBRATION_KEYS, tx=pending)
        self.assertEqual(self.update(2, tx=CalibrationTransmission()).phase, 'idle')
        self.update(3)
        self.assertEqual(self.update(4, keys=0).phase, 'stage')

    def test_absolute_stage_timing_and_capture_instants(self):
        self.update(3)
        for now, stage, pose, seconds, progress in (
            (3, 1, 'FISTS', 5, 0), (7, 1, 'FISTS', 1, .8),
            (8, 2, 'OPEN HANDS', 5, 0), (11, 2, 'OPEN HANDS', 2, .6),
            (13, 3, 'FISTS', 5, 0), (16, 3, 'FISTS', 2, .6)):
            frame = self.update(now)
            self.assertEqual((frame.stage, frame.title, frame.remaining), (stage, pose, seconds))
            self.assertAlmostEqual(frame.progress, progress)
        self.assertEqual(self.update(18).phase, 'verifying')

    def test_skipped_frames_catch_up_without_shifting_schedule(self):
        self.update(3)
        self.assertEqual(self.update(14).stage, 3)
        self.assertEqual(self.guide.frame(18).phase, 'verifying')

    def test_confirmation_requires_new_run_reset_and_both_bits(self):
        self.update(3, calibrated(packet(sequence=1)))
        self.update(4, packet(sequence=2))
        self.assertEqual(self.update(17, calibrated(packet(sequence=3))).phase, 'stage')
        self.assertEqual(self.update(18.1, packet(sequence=4)).phase, 'verifying')
        self.assertEqual(self.update(18.6, calibrated(packet(sequence=5))).phase, 'complete')

    def test_old_success_cannot_verify_new_attempt(self):
        self.update(3, calibrated(packet(sequence=1)))
        self.assertEqual(self.update(18.6, calibrated(packet(sequence=2))).phase, 'verifying')
        self.assertEqual(self.update(19.5, calibrated(packet(sequence=3))).phase, 'failed')

    def test_each_completion_bit_is_required(self):
        for missing in ('orientation', 'flex'):
            with self.subTest(missing=missing):
                self.guide = CalibrationGuide()
                self.update(3)
                self.update(4)
                data = calibrated(packet(sequence=200))
                data = dataclasses.replace(data, **(
                    {'state_flags': data.state_flags & ~(1 << 6)} if missing == 'orientation'
                    else {'validity_flags': data.validity_flags & ~(1 << 13)}))
                self.assertEqual(self.update(19.5, data).phase, 'failed')

    def test_countdown_alone_times_out(self):
        self.update(3)
        self.update(4)
        self.assertEqual(self.update(18).phase, 'verifying')
        frame = self.update(19.5)
        self.assertEqual(frame.phase, 'failed')
        self.assertIn('confirmation timed out', frame.detail)

    def test_stale_or_lost_sources_fail_even_after_success(self):
        for when in (4, 9, 14, 18.2, 18.9):
            for source in ('stale', 'usb', 'link', 'imu'):
                with self.subTest(when=when, source=source):
                    self.guide = CalibrationGuide()
                    self.update(3)
                    self.update(3.1)
                    if when > 18.8:
                        self.update(18.8, calibrated(packet(sequence=100)))
                    data = calibrated(packet(sequence=200))
                    if source == 'stale':
                        data = None
                    elif source == 'link':
                        data = dataclasses.replace(data, state_flags=data.state_flags & ~(1 << 1))
                    elif source == 'imu':
                        data = dataclasses.replace(data, state_flags=data.state_flags & ~(1 << 5))
                    self.guide.update(data, source != 'usb', 0, self.tx, now=when)
                    self.assertEqual(self.guide.frame(when).phase, 'failed')

    def test_disconnected_launch_is_quiet_and_attempt_is_bounded(self):
        tx = CalibrationTransmission()
        self.guide.update(None, False, 0, tx, now=0)
        self.assertEqual(self.guide.frame(0).phase, 'idle')
        self.guide.update(None, False, CALIBRATION_KEYS, tx, now=1)
        self.assertEqual(self.guide.frame(1).phase, 'unavailable')
        self.guide.update(None, False, CALIBRATION_KEYS, tx, now=4)
        self.assertEqual(self.guide.frame(4).phase, 'idle')

    def test_missing_write_times_out_without_starting_stages(self):
        tx = CalibrationTransmission(0)
        self.update(0, keys=CALIBRATION_KEYS, tx=tx)
        self.assertEqual(self.update(4, keys=CALIBRATION_KEYS, tx=tx).phase, 'failed')

    def test_extra_chord_does_not_restart_active_guide(self):
        self.update(3)
        frame = self.update(9, tx=CalibrationTransmission(5, 2, 8))
        self.assertEqual((frame.stage, self.guide.started), (2, 3))

    def test_retry_requires_new_transmission_and_dismiss_sends_nothing(self):
        self.update(3)
        self.update(19.5)
        self.guide.dismiss()
        self.assertEqual(self.update(20).phase, 'idle')
        self.assertEqual(self.update(24, tx=CalibrationTransmission(21, 2, 24)).stage, 1)

    def test_serial_observer_tracks_filtered_mask_and_first_write_only(self):
        observer, hold = CalibrationTransmissionObserver(), CalibrationHold()
        for tick in range(300):
            now = tick / 100
            sent = hold.filter(CALIBRATION_KEYS, now)
            observer.record(hold.started, sent, now)
            self.assertEqual(observer.snapshot().run, 0)
        sent = hold.filter(CALIBRATION_KEYS, 3)
        observer.record(hold.started, sent, 3.001)
        observer.record(hold.started, sent, 3.011)
        self.assertEqual(observer.snapshot(), CalibrationTransmission(0, 1, 3.001))
        observer.record(None, hold.filter(0, 4), 4)
        for tick in range(301):
            now = 5 + tick / 100
            observer.record(5, hold.filter(CALIBRATION_KEYS, now), now)
        self.assertEqual(observer.snapshot().run, 2)

    def test_sidebar_waits_for_same_transmission(self):
        status = CalibrationStatus()
        status.update(packet(), CALIBRATION_KEYS, True, now=0,
                      transmission=CalibrationTransmission(0))
        self.assertEqual(status.update(packet(), CALIBRATION_KEYS, True, now=3.05,
                         transmission=CalibrationTransmission(0)), 'NOT CALIBRATED')
        self.assertEqual(status.update(packet(), CALIBRATION_KEYS, True, now=3.1,
                         transmission=CalibrationTransmission(0, 1, 3.08)), 'CALIBRATING')
        self.assertEqual(status.request_started, 3.08)
        status.update(packet(sequence=2), 0, True, now=4,
                      transmission=CalibrationTransmission(None, 1, 3.08))
        status.update(packet(sequence=3), CALIBRATION_KEYS, True, now=8,
                      transmission=CalibrationTransmission(5, 2, 8))
        self.assertEqual(status.request_started, 3.08)


if __name__ == '__main__':
    unittest.main()
