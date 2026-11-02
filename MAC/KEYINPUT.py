import struct
import threading
import time

from pynput import keyboard
from calibration_status import CalibrationHold

SYNC_1 = 0xA5
SYNC_2 = 0x5A 

PROTOCOL_VERSION = 1
MESSAGE_KEY_STATE = 0x21

PAYLOAD_LENGTH = 6
KEY_BITS = {

    # STANDARD KEYS

    "w":     1 << 0,  # Pitch forward 
    "s":     1 << 1,  # Pitch backward 
    "a":     1 << 2,  # Roll left
    "d":     1 << 3,  # Roll right

    "up":    1 << 4,  # Climb 
    "down":  1 << 5,  # Descend
    "left":  1 << 6,  # Yaw left
    "right": 1 << 7,  # Yaw right
    
    # SPECIAL COMMANDS

    "esc":   1 << 8,  # RTH hold
    "l":     1 << 9,  # LAND hold
    "b":     1 << 10, # BUZZER

    # MODE CHANGE

    "1":     1 << 11, # KEYBOARD
    "2":     1 << 12, # GLOVE
    "3":     1 << 13, # ELRS
}

held_keys = set()

held_keys_lock = threading.Lock()
calibration_hold = CalibrationHold()

SPECIAL_KEYS = {
    keyboard.Key.up:    "up",
    keyboard.Key.down:  "down",
    keyboard.Key.left:  "left",
    keyboard.Key.right: "right",
    keyboard.Key.esc:   "esc",

    keyboard.Key.cmd_l: "cmd",
    keyboard.Key.cmd_r: "cmd",
    keyboard.Key.shift: "shift",
    keyboard.Key.shift_l: "shift",
    keyboard.Key.shift_r: "shift",
}

def normalize_key(key):
    if isinstance(key, keyboard.KeyCode):
        if key.char is None:
            return None

        character = key.char.lower()
        character = {"!": "1", "@": "2", "#": "3"}.get(character, character)
        
        if character in {"w", "a", "s", "d", "l", "b", "1", "2", "3"}:
            return character
        
        return None
    
    return SPECIAL_KEYS.get(key)

def on_key_press(key):
    normalized = normalize_key(key)
    if normalized is None:
        return
    with held_keys_lock:
        held_keys.add(normalized)

def on_key_release(key):
    normalized = normalize_key(key)
    if normalized is None:
        return
    with held_keys_lock:
        held_keys.discard(normalized)

def create_key_mask():
    mask = 0
    
    with held_keys_lock:
        command_chord = {"cmd", "shift"}.issubset(held_keys)
        calibration_chord = {"1", "2", "3"}.issubset(held_keys)
        for key_name in held_keys:
            if key_name in KEY_BITS:
                if key_name in {"esc", "l", "1", "2", "3"}:
                    if not command_chord and not (calibration_chord and key_name in {"1", "2", "3"}):
                        continue
                elif key_name != "b" and ("cmd" in held_keys or "shift" in held_keys):
                    # ARM/DISARM shortcuts must not also command roll.
                    continue
                mask |= KEY_BITS[key_name]

        if "cmd" in held_keys and "shift" in held_keys and "a" in held_keys:
            mask |= (1 << 14)   # ARM

        if "cmd" in held_keys and "shift" in held_keys and "d" in held_keys:
            mask |= (1 << 15)   # DISARM
    
    return mask


def crc16_ccitt_false(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

def build_keyboard_packet(sequence, key_mask):
    """
    Packet layout:
    sync1          uint8
    sync2          uint8
    version        uint8
    message_type   uint8
    payload_length uint16
    sequence       uint16
    timestamp_ms   uint32
    key_mask       uint16
    crc16          uint16
    """
    key_mask = calibration_hold.filter(key_mask)
    timestamp_ms = (time.monotonic_ns() // 1000000) & 0xFFFFFFFF
    body = struct.pack(
        "<BBHHIH",
        PROTOCOL_VERSION,
        MESSAGE_KEY_STATE,
        PAYLOAD_LENGTH,
        sequence,
        timestamp_ms,
        key_mask,
    )
    crc = crc16_ccitt_false(body)
    return (bytes((SYNC_1, SYNC_2)) + body + struct.pack("<H", crc))
