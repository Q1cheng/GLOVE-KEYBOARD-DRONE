import threading
import time
import struct
import os

import serial
import KEYINPUT
import telemetry
from calibration_guide import CalibrationTransmissionObserver
from command_guide import CommandTransmissionObserver

SERIAL_PORT = os.environ.get("FLIGHT_DECK_SERIAL_PORT", "/dev/cu.usbmodem5C380386111")
BAUD_RATE = 115200
SEND_RATE_HZ = 100
SEND_INTERVAL_SECONDS = 1.0 / SEND_RATE_HZ


class SerialLink:
    def __init__(self):
        self.serial_port = None
        self.sequence = 0

        self.stop_event = threading.Event()
        self.shutdown_event = threading.Event()
        self.connection_thread = None
        self.send_thread = None
        self.receive_thread = None
        self.calibration_observer = CalibrationTransmissionObserver()
        self.command_observer = CommandTransmissionObserver()

    def get_calibration_transmission(self):
        return self.calibration_observer.snapshot()

    def get_command_transmission(self):
        return self.command_observer.snapshot()

    def start(self):
        if self.connection_thread is not None and self.connection_thread.is_alive():
            return
        self.shutdown_event.clear()
        self.connection_thread = threading.Thread(
            target=self._connection_loop, name="serial-reconnect", daemon=True)
        self.connection_thread.start()

    def _connection_loop(self):
        while not self.shutdown_event.is_set():
            try:
                self._start_connection()
                while not self.shutdown_event.wait(.05) and not self.stop_event.is_set():
                    pass
            except (serial.SerialException, OSError):
                pass
            finally:
                self.stop_event.set()
                for worker in (self.send_thread, self.receive_thread):
                    if worker is not None:
                        worker.join()
                if self.shutdown_event.is_set():
                    try:
                        self._send_neutral_packets()
                    except (serial.SerialException, OSError):
                        pass
                port = self.serial_port
                self.serial_port = None
                if port is not None:
                    try:
                        port.close()
                    except (serial.SerialException, OSError):
                        pass
            if self.shutdown_event.wait(1):
                break

    def _start_connection(self):
        self.serial_port = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            timeout=0.02,
            write_timeout=0.1,
        )

        self.stop_event.clear()
        telemetry.reset_connection()
        self.calibration_observer = CalibrationTransmissionObserver()
        self.command_observer = CommandTransmissionObserver()

        self.send_thread = threading.Thread(
            target=self._send_loop,
            name="keyboard-send",
            daemon=True,
        )

        self.receive_thread = threading.Thread(
            target=self._receive_loop,
            name="telemetry-receive",
            daemon=True,
        )

        self.receive_thread.start()
        self.send_thread.start()

    def stop(self):
        self.shutdown_event.set()
        self.stop_event.set()

        if self.connection_thread is not None:
            self.connection_thread.join()

        if self.send_thread is not None:
            self.send_thread.join(timeout=1.0)

        if self.receive_thread is not None:
            self.receive_thread.join(timeout=1.0)

        try:
            self._send_neutral_packets()
        except (serial.SerialException, OSError):
            # An unplugged port cannot receive the shutdown packets.
            pass
        finally:
            if self.serial_port is not None:
                try:
                    self.serial_port.close()
                finally:
                    self.serial_port = None

    def _send_loop(self):
        next_send_time = time.monotonic()
        # A key held across reconnection must be released before it can act again.
        blocked_mask = KEYINPUT.create_key_mask()

        while not self.stop_event.is_set():
            key_mask = KEYINPUT.create_key_mask()
            blocked_mask &= key_mask
            key_mask &= ~blocked_mask

            packet = KEYINPUT.build_keyboard_packet(
                sequence=self.sequence,
                key_mask=key_mask,
            )

            transmitted_at = time.monotonic()
            try:
                written = self.serial_port.write(packet)
            except (serial.SerialException, OSError):
                self.stop_event.set()
                return
            if written != len(packet):
                self.stop_event.set()
                return
            if written == len(packet):
                # Observe successful writes only; Right accepts and times holds.
                sent_mask = struct.unpack_from("<H", packet, 12)[0]
                self.calibration_observer.record(
                    KEYINPUT.calibration_hold.started, sent_mask, transmitted_at)
                self.command_observer.record(sent_mask, transmitted_at)
            self.sequence = (self.sequence + 1) & 0xFFFF

            next_send_time += SEND_INTERVAL_SECONDS
            sleep_time = next_send_time - time.monotonic()

            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_send_time = time.monotonic()

    def _receive_loop(self):
        while not self.stop_event.is_set():
            try:
                received_data = self.serial_port.read(512)
            except (serial.SerialException, OSError):
                self.stop_event.set()
                return

            if received_data:
                telemetry.process_received_data(received_data)

    def _send_neutral_packets(self):
        if self.serial_port is None:
            return

        for _ in range(5):
            packet = KEYINPUT.build_keyboard_packet(
                sequence=self.sequence,
                key_mask=0,
            )

            self.serial_port.write(packet)
            self.sequence = (self.sequence + 1) & 0xFFFF
            time.sleep(0.01)
