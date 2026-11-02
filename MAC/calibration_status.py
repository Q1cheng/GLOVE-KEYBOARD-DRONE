"""Presentation of a locally requested calibration and verified completion."""
import time


CALIBRATION_KEYS = (1 << 11) | (1 << 12) | (1 << 13)
CALIBRATION_HOLD_SECONDS = 3.0
# Right's sequence ends after 15.5 s. Allow one telemetry freshness interval
# for its result; expiration never counts as successful calibration.
CALIBRATION_RESULT_TIMEOUT_SECONDS = 16.5


class CalibrationHold:
    """Observe the chord; Right, not the Mac, enforces its three-second hold."""
    def __init__(self):
        self.started = None

    def filter(self, key_mask, now=None):
        now = time.monotonic() if now is None else now
        if key_mask & CALIBRATION_KEYS != CALIBRATION_KEYS:
            self.started = None
            return key_mask
        if self.started is None:
            self.started = now
        return key_mask


class CalibrationStatus:
    def __init__(self):
        self.hold_started = None
        self.request_started = None
        self.chord_triggered = False
        self.saw_incomplete = False
        self.request_packet = None
        self.transmission_run = 0

    def update(self, data, key_mask, usb_open, now=None, transmission=None):
        now = time.monotonic() if now is None else now
        held = key_mask & CALIBRATION_KEYS == CALIBRATION_KEYS
        if not held:
            self.hold_started = None
            self.chord_triggered = False
        elif self.hold_started is None:
            self.hold_started = now

        available = bool(data and usb_open and data.ground_link_valid
                         and data.left_glove_valid and data.left_imu_valid
                         and data.right_imu_valid)
        if not available:
            self.request_started = None
            self.hold_started = None
            return "UNAVAILABLE"

        new_transmission = transmission is not None and transmission.run > self.transmission_run
        if transmission is not None:
            self.transmission_run = transmission.run
            if (self.request_started is not None
                    and now - self.request_started < CALIBRATION_RESULT_TIMEOUT_SECONDS):
                new_transmission = False
        local_hold = (transmission is None and held and not self.chord_triggered and self.hold_started is not None
                and now - self.hold_started >= CALIBRATION_HOLD_SECONDS
                and data.keyboard_packet_valid)
        disarmed = (data.fc_telemetry_valid and data.inav_status_valid and
                    not data.fc_armed and not data.arm_command and not key_mask & (1 << 14))
        if (new_transmission or local_hold) and disarmed:
            self.chord_triggered = True
            self.request_started = transmission.transmitted_at if new_transmission else now
            self.request_packet = (data.sequence, data.timestamp_ms)
            self.saw_incomplete = False

        complete = data.glove_orientation_calibrated and data.flex_calibration_valid
        if self.request_started is not None:
            new_packet = (data.sequence, data.timestamp_ms) != self.request_packet
            self.saw_incomplete |= bool(new_packet and not complete)
            if new_packet and self.saw_incomplete and complete:
                self.request_started = None
                return "CALIBRATED"
            if now - self.request_started < CALIBRATION_RESULT_TIMEOUT_SECONDS:
                # v1 has completion bits, but no explicit progress bit. This is
                # a pending local request, never timer-derived completion.
                return "CALIBRATING"
            if not self.saw_incomplete:
                return "UNAVAILABLE"
            return "NOT CALIBRATED"

        return "CALIBRATED" if complete else "NOT CALIBRATED"
