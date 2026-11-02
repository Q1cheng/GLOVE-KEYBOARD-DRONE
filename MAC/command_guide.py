"""Read-only keyboard-command feedback, using serial observations and telemetry."""
from dataclasses import dataclass
import math
import threading
import time

from calibration_guide import GuideFrame
from calibration_status import CALIBRATION_KEYS

CONFIRMATION_TIMEOUT_SECONDS = 3.0
LAND_OBSERVATION_SECONDS = 9.0
RESULT_DISPLAY_SECONDS = 2.0


@dataclass(frozen=True)
class Command:
    name: str
    bit: int
    seconds: float
    shortcut: str
    mode: int = 0


# Display priority only. Right times independent non-mode keys concurrently.
COMMANDS = (
    Command('DISARM', 15, 3, 'CMD + SHIFT + D'),
    Command('ARM', 14, 3, 'CMD + SHIFT + A'),
    Command('RTH', 8, 5, 'CMD + SHIFT + ESC'),
    Command('LAND', 9, 3, 'CMD + SHIFT + L'),
    Command('KEYBOARD MODE', 11, 3, 'CMD + SHIFT + 1', 1),
    Command('GLOVE MODE', 12, 3, 'CMD + SHIFT + 2', 2),
    Command('ELRS MODE', 13, 3, 'CMD + SHIFT + 3', 3),
    Command('BUZZER', 10, 1, 'B'),
)
ACTION_MASK = sum(1 << command.bit for command in COMMANDS)


@dataclass(frozen=True)
class CommandTransmission:
    started: tuple = ()
    written_at: float | None = None

    def since(self, bit):
        return dict(self.started).get(bit)


class CommandTransmissionObserver:
    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot = CommandTransmission()

    def record(self, sent_mask, written_at):
        with self._lock:
            previous = dict(self._snapshot.started)
            if self._snapshot.written_at is not None and written_at - self._snapshot.written_at >= .15:
                previous = {}
            mode_count = (sent_mask & CALIBRATION_KEYS).bit_count()
            started = tuple((command.bit, previous.get(command.bit, written_at))
                            for command in COMMANDS if sent_mask & (1 << command.bit)
                            and (not command.mode or mode_count == 1)
                            and not (command.bit == 14 and sent_mask & (1 << 15)))
            self._snapshot = CommandTransmission(started, written_at)

    def snapshot(self):
        with self._lock:
            return self._snapshot


class CommandGuide:
    def __init__(self):
        self.phase = 'idle'
        self.command = None
        self.consumed = 0
        self.started = None
        self.pressed_at = None
        self.wait_packet = None
        self.deadline = None
        self.expires = 0
        self.title = self.detail = ''
        self.confirmed = False
        self.extra_modes_shown = False

    @staticmethod
    def _packet_id(data):
        return (data.sequence, data.timestamp_ms) if data else None

    @staticmethod
    def _source_error(data, usb_open):
        if not usb_open:
            return 'USB NOT CONNECTED'
        if data is None:
            return 'Telemetry unavailable.'
        if not data.ground_link_valid:
            return 'RIGHT to AIR link unavailable.'
        return ''

    def _finish(self, title, detail, now, *, failed=False, confirmed=False):
        self.phase = 'failed' if failed else 'result'
        self.title, self.detail = title, detail
        self.confirmed = confirmed
        self.expires = now + RESULT_DISPLAY_SECONDS

    def _not_confirmed(self):
        if self.command.mode:
            return 'MODE CHANGE NOT CONFIRMED'
        if self.command.name in ('ARM', 'DISARM'):
            return self.command.name + ' NOT CONFIRMED'
        return self.command.name + ' NOT CONFIRMED'

    def _confirmation(self, data):
        if self.command.mode:
            return self.command.name + ' SELECTED' if data.current_mode == self.command.mode else None
        if not data.fc_telemetry_valid:
            return None
        if self.command.name in ('ARM', 'DISARM') and data.inav_status_valid:
            if data.fc_armed == (self.command.name == 'ARM'):
                return 'ARMED' if data.fc_armed else 'DISARMED'
        if self.command.name == 'LAND' and data.navigation_status_valid:
            if data.landed:
                return 'LANDED'
            if data.landing_active:
                return 'LANDING ACTIVE'
        if self.command.name == 'RTH' and data.navigation_status_valid and data.rth_active:
            return 'RTH ACTIVE'
        return None

    def update(self, data, usb_open, key_mask, transmission, *, reserved=False, now=None):
        now = time.monotonic() if now is None else now
        self.consumed &= key_mask
        mode_count = (key_mask & CALIBRATION_KEYS).bit_count()
        if reserved or mode_count == 3:
            # Emergency actions remain visible and usable during calibration.
            blocked = CALIBRATION_KEYS | (1 << 14)
            self.consumed |= key_mask & blocked
            if self.command and (1 << self.command.bit) & blocked:
                self.phase = 'idle'
            if mode_count == 3 and self.phase in ('result', 'failed'):
                self.phase = 'idle'
        if mode_count != 2:
            self.extra_modes_shown = False
        else:
            # Right resets all mode timers while two mode keys are held.
            self.consumed &= ~CALIBRATION_KEYS
            if self.command and self.command.mode:
                self.phase = 'idle'

        eligible = key_mask & ACTION_MASK & ~self.consumed
        if self.phase == 'hold' and self.command:
            eligible |= key_mask & (1 << self.command.bit)
        if mode_count != 1:
            eligible &= ~CALIBRATION_KEYS
        if key_mask & (1 << 15):
            eligible &= ~(1 << 14)
        candidate = next((command for command in COMMANDS if eligible & (1 << command.bit)), None)
        if mode_count == 2 and (candidate is None or candidate.name == 'BUZZER'):
            if self.phase not in ('hold', 'waiting') and not self.extra_modes_shown:
                self.command = None
                self._finish('RELEASE EXTRA MODE KEY', 'Hold only one mode key.', now)
                self.extra_modes_shown = True
            self.consumed |= key_mask & (ACTION_MASK & ~CALIBRATION_KEYS)
            candidate = None

        # Only a higher-priority new key interrupts an active command. Keys
        # already down are consumed so they cannot silently queue for later.
        active = self.phase in ('hold', 'waiting')
        preempt = candidate and (not active or COMMANDS.index(candidate) < COMMANDS.index(self.command))
        if preempt:
            self.command = candidate
            self.started = transmission.since(candidate.bit)
            self.pressed_at = now
            self.phase = 'hold'
            self.confirmed = False
            error = self._source_error(data, usb_open)
            if error:
                self._finish(candidate.name + ' UNAVAILABLE', error, now, failed=True)
            elif candidate.name == 'LAND':
                self._finish('LAND UNAVAILABLE', 'Landing integration not enabled.', now, failed=True)
            elif candidate.mode and data.current_mode == candidate.mode:
                self._finish(candidate.name + ' ALREADY SELECTED', '', now, confirmed=True)
        self.consumed |= key_mask & (ACTION_MASK if mode_count != 2 else ACTION_MASK & ~CALIBRATION_KEYS)

        if self.phase == 'hold':
            if not key_mask & (1 << self.command.bit):
                self.phase = 'idle'
                return
            error = self._source_error(data, usb_open)
            if error:
                self._finish(self.command.name + ' UNAVAILABLE', error, now, failed=True)
                return
            observed = transmission.since(self.command.bit)
            if observed is not None:
                self.started = observed
            if (self.started is None or transmission.written_at is None
                    or now - transmission.written_at >= .15):
                if now - self.pressed_at >= 1:
                    self._finish(self.command.name + ' NOT CONFIRMED',
                                 'Keyboard transmission not confirmed.', now, failed=True)
                return
            if now - self.started >= self.command.seconds:
                if self.command.name == 'BUZZER':
                    self._finish('BUZZER TOGGLE REQUESTED', 'Hold completed; buzzer state is not reported.', now)
                else:
                    self.phase = 'waiting'
                    self.wait_packet = self._packet_id(data)
                    wait = LAND_OBSERVATION_SECONDS if self.command.name == 'LAND' else CONFIRMATION_TIMEOUT_SECONDS
                    self.deadline = now + wait
                    self.title = self.command.name + ' REQUESTED'
                    self.detail = 'Waiting for flight-controller state.' if not self.command.mode else 'Waiting for reported mode.'
            return

        if self.phase == 'waiting':
            error = self._source_error(data, usb_open)
            if error:
                self._finish(self._not_confirmed(), error, now, failed=True)
                return
            confirmed = self._confirmation(data) if self._packet_id(data) != self.wait_packet else None
            if confirmed:
                if self.command.name != 'LAND' or confirmed == 'LANDED':
                    self._finish(confirmed, '', now, confirmed=True)
                    return
                self.title, self.detail = confirmed, ''
            elif self.command.name == 'LAND':
                self.title, self.detail = 'LAND REQUESTED', 'Landing state not confirmed.'
            if now >= self.deadline:
                if self.command.name == 'LAND':
                    self._finish(self.title if confirmed else 'LAND NOT CONFIRMED',
                                 self.detail, now, failed=not bool(confirmed), confirmed=bool(confirmed))
                else:
                    self._finish(self._not_confirmed(), 'No valid confirmation received.', now, failed=True)
            return

        if self.phase in ('result', 'failed'):
            if self.confirmed:
                error = self._source_error(data, usb_open)
                if error or not self._confirmation(data):
                    self._finish(self._not_confirmed(), error or 'Reported state changed or is unavailable.',
                                 now, failed=True)
            if now >= self.expires:
                self.phase = 'idle'

    def frame(self, now=None):
        now = time.monotonic() if now is None else now
        if self.phase == 'hold':
            elapsed = max(0, now - self.started) if self.started is not None else 0
            return GuideFrame('hold', self.command.name,
                              'HOLD ' + self.command.shortcut + '  |  Release to cancel',
                              max(0, math.ceil(self.command.seconds - elapsed)),
                              min(1, elapsed / self.command.seconds))
        return GuideFrame(self.phase, self.title, self.detail)
