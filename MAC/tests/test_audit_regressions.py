import importlib.util
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import telemetry
import UI
from test_sidebar_status import packet


def wire_packet(sequence=1, timestamp=50):
    data = bytearray(telemetry.TELEMETRY_PACKET_LENGTH)
    data[:6] = b"\xa5\x5a\x01\x51\x00\x67"
    struct.pack_into(">HI", data, 6, sequence, timestamp)
    struct.pack_into(">H", data, 111, telemetry.crc16_ccitt_false(data[2:111]))
    return bytes(data)


class SerialFailureTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "audit_serial_link", Path(__file__).resolve().parents[1] / "serial_link.py")
        self.module = importlib.util.module_from_spec(spec)
        keys = SimpleNamespace(create_key_mask=lambda: 0,
                               build_keyboard_packet=lambda **kwargs: bytes(16),
                               calibration_hold=SimpleNamespace(started=None))
        with patch.dict(sys.modules, {"KEYINPUT": keys}):
            spec.loader.exec_module(self.module)
        self.link = self.module.SerialLink()
        self.port = Mock()
        self.link.serial_port = self.port

    def test_disconnect_still_closes_port(self):
        self.port.write.side_effect = self.module.serial.SerialException("unplugged")
        self.link.stop()
        self.port.close.assert_called_once()
        self.assertIsNone(self.link.serial_port)

    def test_healthy_stop_preserves_five_neutral_packets(self):
        with patch.object(self.module.time, "sleep"):
            self.link.stop()
        self.assertEqual(self.port.write.call_count, 5)
        self.assertEqual(self.link.sequence, 5)
        self.port.close.assert_called_once()

    def test_worker_io_errors_stop_both_workers(self):
        for method, operation in (("_send_loop", "write"), ("_receive_loop", "read")):
            for error in (OSError("unplugged"), self.module.serial.SerialException("unplugged")):
                with self.subTest(method=method, error=type(error).__name__):
                    self.link.stop_event.clear()
                    getattr(self.port, operation).side_effect = error
                    getattr(self.link, method)()
                    self.assertTrue(self.link.stop_event.is_set())


class HeaderArmTests(unittest.TestCase):
    def render_arm(self, data, age=0):
        ui = SimpleNamespace(
            get_telemetry=lambda: data, get_telemetry_age=lambda: age,
            get_parser_stats=lambda: telemetry.TelemetryParserStats(),
            _update_rates=Mock(), _serial_open=lambda: True,
            video_capture=SimpleNamespace(get_latest_frame_info=lambda: (None, None, 0)),
            header_labels={name: Mock() for name in
                           ("usb", "air", "mode", "arm", "telemetry", "camera")},
            telemetry_hz=20, _update_video=Mock(), serial_link=SimpleNamespace(),
            get_key_mask=lambda: 0, calibration_guide=Mock(phase="idle"),
            command_guide=Mock(phase="idle"), calibration_overlay=None,
            _update_telemetry_labels=Mock(), _update_warnings=Mock())
        UI.FlightDeckUI._update_data(ui)
        return ui.header_labels["arm"].configure.call_args.kwargs

    def test_arm_state_requires_fresh_valid_fc_status(self):
        for armed in (False, True):
            state = (1 << telemetry.STATE_FLAGS["fc_armed"]) if armed else 0
            valid = packet(state_flags=state)
            self.assertEqual(self.render_arm(valid)["text"], "ARMED" if armed else "DISARMED")
            for flag in ("fc_telemetry", "inav_status"):
                invalid = packet(state_flags=state, validity_flags=
                                 valid.validity_flags & ~(1 << telemetry.VALIDITY_FLAGS[flag]))
                self.assertEqual(self.render_arm(invalid), {"text": "ARM --", "fg": UI.MUTED})
            self.assertEqual(self.render_arm(valid, age=1)["text"], "ARM --")
        self.assertEqual(self.render_arm(None)["text"], "ARM --")


class DuplicateTelemetryTests(unittest.TestCase):
    def test_duplicate_does_not_refresh_age_or_inflate_retention(self):
        parser = telemetry.TelemetryStreamParser()
        with patch.object(telemetry, "telemetry_parser", parser), \
                patch.object(telemetry, "latest_telemetry", None), \
                patch.object(telemetry, "latest_telemetry_received_at", None), \
                patch.object(telemetry.time, "monotonic", return_value=1) as clock:
            raw = wire_packet()
            telemetry.process_received_data(raw)
            clock.return_value = 10
            telemetry.process_received_data(raw[:20])
            telemetry.process_received_data(raw[20:])
            self.assertEqual(telemetry.latest_telemetry_received_at, 1)
            self.assertEqual(parser.stats.packets_parsed, 1)
            telemetry.process_received_data(wire_packet(3, 150))
            self.assertEqual(telemetry.latest_telemetry_received_at, 10)
            self.assertEqual(parser.stats.sequence_gaps, 1)

    def test_sequence_wrap_and_same_sequence_with_new_timestamp_are_accepted(self):
        parser = telemetry.TelemetryStreamParser()
        self.assertEqual(len(parser.feed(wire_packet(65535) + wire_packet(0, 100))), 2)
        self.assertEqual(parser.stats.sequence_gaps, 0)
        self.assertEqual(len(parser.feed(wire_packet(0, 150))), 1)


if __name__ == "__main__":
    unittest.main()
