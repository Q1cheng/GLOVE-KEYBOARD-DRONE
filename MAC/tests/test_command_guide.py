import dataclasses
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from command_guide import CommandGuide, CommandTransmissionObserver, COMMANDS
from calibration_status import CALIBRATION_KEYS
from test_sidebar_status import packet


def state(sequence=1, mode=1, armed=False, landing=False, landed=False, **changes):
    data = packet(sequence=sequence, timestamp_ms=sequence*50, current_mode=mode)
    data = dataclasses.replace(data,
        validity_flags=data.validity_flags | (1 << 9) | (1 << 10),
        state_flags=data.state_flags | (int(armed) << 11) | (int(landing) << 14) | (int(landed) << 15))
    return dataclasses.replace(data, **changes)


class CommandGuideTests(unittest.TestCase):
    def setUp(self):
        self.guide = CommandGuide()
        self.observer = CommandTransmissionObserver()

    def step(self, now, mask=0, data='default', usb=True, reserved=False, write=True):
        if data == 'default':
            data = state(sequence=int(now * 100)+1)
        if write:
            # Continuous successful writes between UI samples, as at 100 Hz.
            snapshot = self.observer.snapshot()
            if snapshot.written_at is not None:
                previous_mask = sum(1 << bit for bit, _ in snapshot.started)
                tick = snapshot.written_at + .01
                while tick < now:
                    self.observer.record(previous_mask, tick)
                    tick += .01
            self.observer.record(mask, now)
        self.guide.update(data, usb, mask, self.observer.snapshot(), reserved=reserved, now=now)
        return self.guide.frame(now)

    def test_all_hardware_hold_times_and_early_release(self):
        for command in COMMANDS:
            if command.name == 'LAND':
                continue
            with self.subTest(command=command.name):
                self.setUp()
                mode = 2 if command.mode == 1 else 1
                mask = 1 << command.bit
                frame = self.step(0, mask, state(mode=mode))
                self.assertEqual(frame.remaining, int(command.seconds))
                self.assertEqual(self.step(command.seconds-.01, mask, state(mode=mode)).phase, 'hold')
                self.assertEqual(self.step(command.seconds-.005, 0, state(mode=mode)).phase, 'idle')

    def test_already_selected_is_brief_and_never_repeats_while_held(self):
        for mode, bit in ((1, 11), (2, 12), (3, 13)):
            self.setUp()
            frame = self.step(0, 1 << bit, state(mode=mode))
            self.assertIn('ALREADY SELECTED', frame.title)
            self.assertIsNone(frame.remaining)
            self.assertEqual(self.step(2.1, 1 << bit, state(mode=mode)).phase, 'idle')
            self.assertEqual(self.step(4, 1 << bit, state(mode=mode)).phase, 'idle')

    def test_mode_waits_for_new_packet_and_can_fail(self):
        self.step(0, 1 << 12)
        self.assertEqual(self.step(3, 1 << 12, state(2, mode=2)).phase, 'waiting')
        self.assertEqual(self.step(3.1, 0, state(2, mode=2)).phase, 'waiting')
        self.assertEqual(self.step(3.2, 0, state(3, mode=2)).title, 'GLOVE MODE SELECTED')
        self.setUp()
        self.step(0, 1 << 13)
        self.step(3, 1 << 13)
        self.assertEqual(self.step(6.1).title, 'MODE CHANGE NOT CONFIRMED')

    def test_arm_disarm_require_valid_fc_state_not_command_bits(self):
        for name, bit, target in (('ARM', 14, True), ('DISARM', 15, False)):
            with self.subTest(name=name):
                self.setUp()
                self.step(0, 1 << bit, state(1, armed=not target))
                self.step(3, 1 << bit, state(2, armed=not target))
                wrong = state(3, armed=not target)
                wrong = dataclasses.replace(wrong, state_flags=wrong.state_flags | (1 << 8))
                self.assertEqual(self.step(3.1, 0, wrong).phase, 'waiting')
                invalid = state(4, armed=target, validity_flags=1)
                self.assertEqual(self.step(3.2, 0, invalid).phase, 'waiting')
                self.assertEqual(self.step(3.3, 0, state(5, armed=target)).title,
                                 'ARMED' if target else 'DISARMED')
                self.assertEqual(self.step(3.4, 0, None).title, name + ' NOT CONFIRMED')

    def test_arm_disarm_unconfirmed_outcomes(self):
        for bit, title, armed in ((14, 'ARM NOT CONFIRMED', False), (15, 'DISARM NOT CONFIRMED', True)):
            self.setUp()
            self.step(0, 1 << bit, state(1, armed=armed))
            self.step(3, 1 << bit, state(2, armed=armed))
            self.assertEqual(self.step(6.1, 0, state(3, armed=armed)).title, title)

    def test_unimplemented_land_is_unavailable_not_requested(self):
        frame = self.step(0, 1 << 9)
        self.assertEqual(frame.title, 'LAND UNAVAILABLE')
        self.assertIsNone(frame.remaining)
        self.assertEqual(self.step(1, 1 << 9).title, 'LAND UNAVAILABLE')

    def test_buzzer_is_request_only_and_requires_release_to_repeat(self):
        self.step(0, 1 << 10)
        frame = self.step(1, 1 << 10)
        self.assertEqual(frame.title, 'BUZZER TOGGLE REQUESTED')
        self.assertEqual(self.step(4, 1 << 10).phase, 'idle')
        self.assertEqual(self.step(5, 1 << 10).phase, 'idle')
        self.step(5.1)
        self.assertEqual(self.step(5.2, 1 << 10).phase, 'hold')

    def test_two_mode_keys_reset_timer_without_queue(self):
        self.step(0, 1 << 12)
        frame = self.step(2, (1 << 12) | (1 << 13))
        self.assertEqual(frame.title, 'RELEASE EXTRA MODE KEY')
        self.assertIsNone(frame.remaining)
        self.assertEqual(self.step(4.1, (1 << 12) | (1 << 13)).phase, 'idle')
        frame = self.step(4.2, 1 << 13)
        self.assertEqual((frame.title, frame.remaining), ('ELRS MODE', 3))
        self.assertEqual(self.step(5.2, 1 << 13).phase, 'hold')
        self.assertEqual(self.step(7.2, 1 << 13).phase, 'waiting')

    def test_calibration_reserves_full_chord_and_suppresses_commands(self):
        self.step(0, 1 << 12)
        self.assertEqual(self.step(1, CALIBRATION_KEYS).phase, 'idle')
        self.assertEqual(self.step(4, CALIBRATION_KEYS).phase, 'idle')
        self.assertEqual(self.step(5, 1 << 15, reserved=True).title, 'DISARM')

    def test_disarm_preempts_arm_and_arm_is_not_queued(self):
        self.step(0, 1 << 14)
        frame = self.step(.4, (1 << 14) | (1 << 15))
        self.assertEqual((frame.title, frame.remaining), ('DISARM', 3))
        self.assertEqual(self.step(.7, 1 << 14).phase, 'idle')
        self.assertEqual(self.step(1.5, 1 << 14).phase, 'idle')

    def test_lower_priority_commands_do_not_queue(self):
        self.step(0, (1 << 15) | (1 << 10))
        self.assertEqual(self.step(.5, 1 << 10).phase, 'idle')
        self.assertEqual(self.step(2, 1 << 10).phase, 'idle')

    def test_disconnected_usb_and_stale_telemetry_are_explicit(self):
        for data, usb, message in ((None, True, 'Telemetry unavailable.'),
                                   (state(), False, 'USB NOT CONNECTED'),
                                   (state(state_flags=0), True, 'RIGHT to AIR link unavailable.')):
            self.setUp()
            frame = self.step(0, 1 << 12, data, usb)
            self.assertEqual(frame.detail, message)
            self.assertNotIn('SELECTED', frame.title)

    def test_lost_link_during_hold_and_confirmation_clears_feedback(self):
        self.step(0, 1 << 12)
        self.assertEqual(self.step(1, 1 << 12, None).phase, 'failed')
        self.setUp()
        self.step(0, 1 << 12)
        self.step(3, 1 << 12)
        frame = self.step(3.1, 0, None)
        self.assertEqual((frame.title, frame.detail), ('MODE CHANGE NOT CONFIRMED', 'Telemetry unavailable.'))

    def test_no_serial_write_cannot_complete_a_hold(self):
        self.step(0, 1 << 10, write=False)
        frame = self.step(1, 1 << 10, write=False)
        self.assertEqual(frame.phase, 'failed')
        self.assertNotIn('REQUESTED', frame.title)

    def test_land_monitor_and_results_have_bounded_visibility(self):
        self.step(0, 1 << 9)
        self.step(3, 1 << 9)
        self.assertEqual(self.step(9.1).title, 'LAND UNAVAILABLE')
        self.assertEqual(self.step(11.2).phase, 'idle')


if __name__ == '__main__':
    unittest.main()
