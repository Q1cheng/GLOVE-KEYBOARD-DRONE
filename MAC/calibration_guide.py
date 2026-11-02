"""Read-only calibration timing and confirmation; never sends commands.

Right supplies no start/capture acknowledgment in Air telemetry. The guide's
clock therefore precedes Right by the unmeasured USB/firmware delivery delay.
Air alone retains control of its existing five-second glove-control lockout.
"""
from dataclasses import dataclass
import math
import threading
import time

from calibration_status import (CALIBRATION_KEYS, CALIBRATION_HOLD_SECONDS,
                                CALIBRATION_RESULT_TIMEOUT_SECONDS)

STAGE_SECONDS = 5.0
GUIDE_SECONDS = 3 * STAGE_SECONDS


@dataclass(frozen=True)
class CalibrationTransmission:
    hold_started: float | None = None
    run: int = 0
    transmitted_at: float | None = None


class CalibrationTransmissionObserver:
    """Share successful serial-write observations with the UI thread."""
    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot = CalibrationTransmission()
        self._chord_sent = False
        self._hold_started = None
        self._last_write = None

    def record(self, hold_started, sent_mask, transmitted_at):
        chord = sent_mask & CALIBRATION_KEYS == CALIBRATION_KEYS
        with self._lock:
            previous = self._snapshot
            if not chord or (self._last_write is not None and transmitted_at - self._last_write >= .15):
                self._hold_started = None
                self._chord_sent = False
            if chord and self._hold_started is None:
                self._hold_started = transmitted_at
            first = (chord and not self._chord_sent and
                     transmitted_at - self._hold_started >= CALIBRATION_HOLD_SECONDS)
            self._snapshot = CalibrationTransmission(
                self._hold_started, previous.run + int(first),
                transmitted_at if first else previous.transmitted_at)
            self._chord_sent |= first
            self._last_write = transmitted_at

    def snapshot(self):
        with self._lock:
            return self._snapshot


@dataclass(frozen=True)
class GuideFrame:
    phase: str
    title: str = ""
    detail: str = ""
    remaining: int | None = None
    progress: float | None = None
    stage: int = 0


class CalibrationGuide:
    def __init__(self):
        self.phase = "idle"
        self.hold_started = None
        self.started = None
        self.last_run = 0
        self.start_packet = None
        self.saw_incomplete = False
        self.reason = ""
        self._released = True
        self.expires = None
        self._rejected_chord = False

    @staticmethod
    def _packet_id(data):
        return (data.sequence, data.timestamp_ms) if data else None

    @staticmethod
    def _source_error(data, usb_open, require_disarmed=True):
        if not usb_open:
            return "USB NOT CONNECTED"
        if data is None or not data.ground_link_valid:
            return "Telemetry unavailable."
        if require_disarmed and (not data.fc_telemetry_valid or not data.inav_status_valid):
            return "ARM STATE UNAVAILABLE"
        if require_disarmed and data.fc_armed:
            return "CALIBRATION UNAVAILABLE WHILE ARMED"
        if require_disarmed and data.arm_command:
            return "ARM REQUEST ACTIVE"
        if not (data.left_glove_valid and data.left_imu_valid and data.right_imu_valid):
            return "Calibration readings unavailable."
        return ""

    def _fail(self, reason, now, unavailable=False):
        self.phase = "unavailable" if unavailable else "failed"
        self.reason = reason
        self.expires = now + 2.0

    def update(self, data, usb_open, key_mask, transmission, now=None):
        now = time.monotonic() if now is None else now
        held = key_mask & CALIBRATION_KEYS == CALIBRATION_KEYS
        if not held:
            self._released = True
            self._rejected_chord = False
        new_run = transmission.run > self.last_run
        self.last_run = transmission.run
        error = self._source_error(data, usb_open)
        if held and key_mask & (1 << 14):
            error = "Release ARM before calibration."
        if held and self._released and self.phase != "running" and error:
            self._released = False
            self._rejected_chord = True
            self._fail(error, now, unavailable=True)
            return
        if new_run and self.phase != "running":
            if error or self._rejected_chord:
                return
            self.started = transmission.transmitted_at
            self.start_packet = self._packet_id(data)
            self.saw_incomplete = False
            self.phase = "running"
            self._released = False

        if self.phase == "running":
            error = self._source_error(data, usb_open)
            if error:
                self._fail(error, now)
                return
            complete = data.glove_orientation_calibrated and data.flex_calibration_valid
            new_packet = self._packet_id(data) != self.start_packet
            if new_packet and not complete:
                self.saw_incomplete = True
            elapsed = now - self.started
            # A previous run's true flags cannot verify this request. Require
            # an observed reset and fresh completion after the timed guide.
            if elapsed >= GUIDE_SECONDS and new_packet and self.saw_incomplete and complete:
                self.phase = "complete"
                self.expires = now + 2.0
            elif elapsed >= CALIBRATION_RESULT_TIMEOUT_SECONDS:
                self._fail("Calibration confirmation timed out.", now)
            return

        if self.phase == "complete":
            error = self._source_error(data, usb_open, require_disarmed=False)
            if error or not (data.glove_orientation_calibrated and data.flex_calibration_valid):
                self._fail(error or "Calibration confirmation unavailable.", now)

        if self.phase in ("complete", "failed", "unavailable") and now >= self.expires:
            self.phase = "idle"

        if held and self._released and self.phase != "hold":
            self.phase = "hold"
            self.hold_started = transmission.hold_started if transmission.hold_started is not None else now
            self._released = False
        if self.phase == "hold":
            if not held:
                self.phase = "idle"
                self.hold_started = None
            else:
                if error:
                    self._rejected_chord = True
                    self._fail(error, now, unavailable=True)
                    return
                if transmission.hold_started is not None:
                    self.hold_started = transmission.hold_started
                elapsed = now - self.hold_started
                if elapsed >= CALIBRATION_HOLD_SECONDS + 1:
                    self._fail("Calibration request was not transmitted.", now)

    def dismiss(self):
        if self.phase in ("complete", "failed", "unavailable"):
            self.phase = "idle"

    def frame(self, now=None):
        now = time.monotonic() if now is None else now
        if self.phase == "hold":
            elapsed = max(0, now - self.hold_started)
            return GuideFrame("hold", "CALIBRATION", "HOLD 1 + 2 + 3  |  Release to cancel",
                              max(0, math.ceil(CALIBRATION_HOLD_SECONDS - elapsed)),
                              min(1, elapsed / CALIBRATION_HOLD_SECONDS))
        if self.phase == "running":
            elapsed = max(0, now - self.started)
            if elapsed < GUIDE_SECONDS:
                stage = int(elapsed // STAGE_SECONDS)
                progress = (elapsed - stage * STAGE_SECONDS) / STAGE_SECONDS
                return GuideFrame("stage", ("FISTS", "OPEN HANDS", "FISTS")[stage],
                    ("Both hands closed. Warm up the flex sensors.",
                     "Both hands forward. Fingers comfortably straight.",
                     "Close both hands and hold steady.")[stage],
                    max(1, math.ceil(STAGE_SECONDS * (1 - progress))), progress, stage + 1)
            return GuideFrame("verifying", "VERIFYING CALIBRATION",
                              "Waiting for calibration confirmation.")
        if self.phase == "complete":
            return GuideFrame("complete", "CALIBRATION COMPLETE", "Both gloves calibrated.")
        if self.phase == "failed":
            return GuideFrame("failed", "CALIBRATION FAILED",
                              self.reason + "\nCheck gloves and try again.")
        if self.phase == "unavailable":
            title = self.reason if self.reason in ("ARM STATE UNAVAILABLE", "CALIBRATION UNAVAILABLE WHILE ARMED") else "CALIBRATION UNAVAILABLE"
            return GuideFrame("unavailable", title, "" if title == self.reason else self.reason)
        return GuideFrame("idle")
