"""Safety/confirmation regressions; no real serial or flight commands."""
import dataclasses
import unittest

from calibration_guide import CalibrationGuide, CalibrationTransmission, CalibrationTransmissionObserver
from calibration_status import CALIBRATION_KEYS, CalibrationStatus
from command_guide import CommandTransmissionObserver, COMMANDS
import test_command_guide
from test_command_guide import state


class CommandSafetyTests(unittest.TestCase):
    setUp = test_command_guide.CommandGuideTests.setUp
    step = test_command_guide.CommandGuideTests.step
    def test_rth_uses_fc_navigation_not_command_bit(self):
        self.step(0, 1 << 8)
        self.assertEqual(self.step(4.99, 1 << 8).remaining, 1)
        self.assertEqual(self.step(5, 1 << 8).title, 'RTH REQUESTED')
        data = state(600)
        commanded = dataclasses.replace(data, state_flags=data.state_flags | (1 << 9))
        self.assertEqual(self.step(5.1, data=commanded).title, 'RTH REQUESTED')
        active = dataclasses.replace(data, sequence=601, state_flags=data.state_flags | (1 << 13))
        invalid = dataclasses.replace(active, validity_flags=1)
        self.assertEqual(self.step(5.2, data=invalid).title, 'RTH REQUESTED')
        self.assertEqual(self.step(5.3, data=active).title, 'RTH ACTIVE')
        self.assertEqual(self.step(5.4, data=None).title, 'RTH NOT CONFIRMED')

    def test_rth_timeout_is_not_unavailable(self):
        self.step(0, 1 << 8)
        self.step(5, 1 << 8)
        self.assertEqual(self.step(8.1).title, 'RTH NOT CONFIRMED')

    def test_every_action_same_usb_unavailable_without_countdown(self):
        for command in COMMANDS:
            self.setUp()
            frame = self.step(0, 1 << command.bit, usb=False)
            self.assertEqual(frame.title, command.name + ' UNAVAILABLE')
            self.assertEqual(frame.detail, 'USB NOT CONNECTED')
            self.assertIsNone(frame.remaining)
            self.assertIsNone(frame.progress)

    def test_write_gap_resets_observed_holds(self):
        observer = CommandTransmissionObserver()
        observer.record(1 << 8, 0)
        observer.record(1 << 8, 5)
        self.assertEqual(observer.snapshot().since(8), 5)
        observer.record((1 << 14) | (1 << 15), 5.01)
        self.assertIsNone(observer.snapshot().since(14))


class CalibrationSafetyTests(unittest.TestCase):
    def test_arming_after_confirmed_completion_does_not_invent_calibration_failure(self):
        from test_sidebar_status import calibrated
        guide = CalibrationGuide()
        tx = CalibrationTransmission(0, 1, 3)
        guide.update(state(1), True, 0, tx, now=3)
        guide.update(state(2), True, 0, tx, now=4)
        guide.update(calibrated(state(3)), True, 0, tx, now=18.6)
        guide.update(calibrated(state(4, armed=True)), True, 0, tx, now=18.7)
        self.assertEqual(guide.phase, 'complete')

    def test_armed_unknown_and_pending_arm_are_not_countdowns(self):
        for data, title in ((state(armed=True), 'CALIBRATION UNAVAILABLE WHILE ARMED'),
                            (state(validity_flags=1), 'ARM STATE UNAVAILABLE'),
                            (None, 'CALIBRATION UNAVAILABLE')):
            guide = CalibrationGuide()
            guide.update(data, True, CALIBRATION_KEYS, CalibrationTransmission(), now=0)
            frame = guide.frame(0)
            self.assertEqual(frame.title, title)
            self.assertIsNone(frame.remaining)
            # No delayed start if state becomes safe while the rejected chord is still held.
            guide.update(state(), True, CALIBRATION_KEYS, CalibrationTransmission(0), now=2.1)
            guide.update(state(), True, CALIBRATION_KEYS, CalibrationTransmission(0, 1, 3), now=3)
            self.assertNotEqual(guide.phase, 'running')

    def test_serial_disconnected_is_immediate_shared_unavailable(self):
        guide = CalibrationGuide()
        guide.update(state(), False, CALIBRATION_KEYS, CalibrationTransmission(), now=0)
        self.assertEqual(guide.frame(0).detail, 'USB NOT CONNECTED')
        self.assertIsNone(guide.frame(0).remaining)

    def test_loss_of_arm_state_during_any_stage_fails(self):
        for now in (4, 9, 14, 18):
            guide = CalibrationGuide()
            tx = CalibrationTransmission(0, 1, 3)
            guide.update(state(), True, 0, tx, now=3)
            guide.update(state(validity_flags=1), True, 0, tx, now=now)
            self.assertEqual(guide.phase, 'failed')
            guide.update(state(), True, 0, tx, now=now+.1)
            self.assertNotEqual(guide.phase, 'complete')

    def test_early_release_and_write_gap_cannot_start_a_run(self):
        observer = CalibrationTransmissionObserver()
        observer.record(0, CALIBRATION_KEYS, 0)
        observer.record(0, CALIBRATION_KEYS, 2.9)
        self.assertEqual(observer.snapshot().run, 0)
        observer.record(None, 0, 3)
        self.assertIsNone(observer.snapshot().hold_started)
        self.assertEqual(observer.snapshot().run, 0)

    def test_rejected_chord_does_not_make_sidebar_calibrating(self):
        for data in (state(armed=True), state(validity_flags=1)):
            status = CalibrationStatus()
            self.assertNotEqual(status.update(data, CALIBRATION_KEYS, True, now=3,
                transmission=CalibrationTransmission(0, 1, 3)), 'CALIBRATING')


if __name__ == '__main__':
    unittest.main()
