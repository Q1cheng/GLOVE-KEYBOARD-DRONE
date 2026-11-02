import struct
import unittest
from unittest.mock import Mock, patch

import telemetry
import test_audit_regressions as audit


class SerialRecoveryTests(unittest.TestCase):
    setUp = audit.SerialFailureTests.setUp
    def test_partial_write_disconnects_instead_of_counting_a_hold(self):
        self.port.write.return_value = 3
        self.link._send_loop()
        self.assertTrue(self.link.stop_event.is_set())
        self.assertIsNone(self.link.command_observer.snapshot().written_at)

    def test_held_keys_must_be_released_after_connection(self):
        sent = []
        masks = iter([1 << 14, 1 << 14, 0, 1 << 14])
        self.module.KEYINPUT.create_key_mask = lambda: next(masks)

        def build(sequence, key_mask):
            sent.append(key_mask)
            packet = bytearray(16)
            struct.pack_into('<H', packet, 12, key_mask)
            if len(sent) == 3:
                self.link.stop_event.set()
            return bytes(packet)

        self.module.KEYINPUT.build_keyboard_packet = build
        self.port.write.return_value = 16
        with patch.object(self.module.time, 'sleep'):
            self.link._send_loop()
        self.assertEqual(sent, [0, 0, 1 << 14])

    def test_connection_can_retry_after_open_failure(self):
        self.link._start_connection = Mock(side_effect=self.module.serial.SerialException('missing'))
        self.link.shutdown_event.wait = Mock(side_effect=lambda seconds: True)
        self.link.serial_port = None
        self.link._connection_loop()
        self.link._start_connection.assert_called_once()
        self.assertTrue(self.link.stop_event.is_set())

    def test_parser_and_display_are_cleared_between_connections(self):
        with patch.object(telemetry, 'telemetry_parser', telemetry.TelemetryStreamParser()), \
                patch.object(telemetry, 'latest_telemetry', None), \
                patch.object(telemetry, 'latest_telemetry_received_at', None):
            telemetry.process_received_data(audit.wire_packet())
            self.assertIsNotNone(telemetry.get_latest_telemetry())
            telemetry.reset_connection()
            self.assertIsNone(telemetry.get_latest_telemetry())
            self.assertEqual(telemetry.get_latest_telemetry_age(), float('inf'))


if __name__ == '__main__':
    unittest.main()
