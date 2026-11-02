import threading
import time
from dataclasses import dataclass


SYNC_BYTES = b"\xA5\x5A"
TELEMETRY_VERSION = 1
TELEMETRY_MESSAGE_TYPE = 0x51
TELEMETRY_PAYLOAD_LENGTH = 103
TELEMETRY_PACKET_LENGTH = 113
# MSP_RC compares CH1-CH8, including the altitude-hold request.
# The rounded percentage uniquely encodes all nine possible match counts.
RC_CHANNELS_CHECKED = 8

CONTROL_MODE_NAMES = {
    0: "None",
    1: "Keyboard",
    2: "Glove",
    3: "ELRS",
}

VALIDITY_FLAGS = {
    "fc_telemetry": 0,
    "gps": 1,
    "vario": 2,
    "battery": 3,
    "barometer": 4,
    "rpm": 5,
    "temperature": 6,
    "attitude": 7,
    "failsafe_status": 8,
    "inav_status": 9,
    "navigation_status": 10,
    "rc_check": 11,
    "home_data": 12,
    "flex_calibration": 13,
}


STATE_FLAGS = {
    "primary_control_valid": 0,
    "ground_link_valid": 1,
    "keyboard_packet_valid": 2,
    "left_glove_valid": 3,
    "left_imu_valid": 4,
    "right_imu_valid": 5,
    "glove_orientation_calibrated": 6,
    "failsafe_active": 7,
    "arm_command": 8,
    "rth_command": 9,
    "land_command": 10,
    "fc_armed": 11,
    "arm_state_matches_command": 12,
    "rth_active": 13,
    "landing_active": 14,
    "landed": 15,
}


class TelemetryParseError(ValueError):
    pass



@dataclass(frozen=True)
class AirTelemetry:
    raw_packet: bytes
    sequence: int
    timestamp_ms: int
    current_mode: int
    validity_flags: int
    state_flags: int
    latitude_e7: int
    longitude_e7: int
    ground_speed_deci_kph: int
    gps_course_centideg: int
    gps_altitude_m: int
    satellite_count: int
    vertical_speed_cms: int
    battery_voltage_deci_v: int
    battery_current_deci_a: int
    mah_used: int
    battery_percent: int
    baro_altitude_dm: int
    motor_rpm: tuple[int, int, int, int]
    esc_temperature_count: int
    esc_temperature_deci_c: tuple[int, int, int, int]
    pitch_rad10000: int
    roll_rad10000: int
    yaw_rad10000: int
    cycle_time_us: int
    i2c_error_count: int
    sensor_status: int
    system_load_percent: int
    config_profile: int
    battery_profile: int
    arming_flags: int
    active_mode_flags_low: int
    active_mode_flags_high: int
    mixer_profile: int
    nav_mode: int
    nav_state: int
    nav_error: int
    rc_accuracy_percent: int
    distance_to_home_m: int
    direction_to_home_deg: int

    @property
    def current_mode_name(self):
        return CONTROL_MODE_NAMES.get(
            self.current_mode,
            f"Unknown({self.current_mode})",
        )

    @property
    def latitude_degrees(self):
        return self.latitude_e7 / 10_000_000.0

    @property
    def longitude_degrees(self):
        return self.longitude_e7 / 10_000_000.0

    @property
    def ground_speed_kph(self):
        return self.ground_speed_deci_kph / 10.0

    @property
    def gps_course_degrees(self):
        return self.gps_course_centideg / 100.0

    @property
    def vertical_speed_mps(self):
        return self.vertical_speed_cms / 100.0

    @property
    def battery_voltage_v(self):
        return self.battery_voltage_deci_v / 10.0

    @property
    def battery_current_a(self):
        return self.battery_current_deci_a / 10.0

    @property
    def baro_altitude_m(self):
        return self.baro_altitude_dm / 10.0

    @property
    def pitch_radians(self):
        return self.pitch_rad10000 / 10_000.0

    @property
    def roll_radians(self):
        return self.roll_rad10000 / 10_000.0

    @property
    def yaw_radians(self):
        return self.yaw_rad10000 / 10_000.0

    def validity(self, name):
        return bool(self.validity_flags & (1 << VALIDITY_FLAGS[name]))

    def state(self, name):
        return bool(self.state_flags & (1 << STATE_FLAGS[name]))

    @property
    def fc_telemetry_valid(self):
        return self.validity("fc_telemetry")

    @property
    def gps_valid(self):
        return self.validity("gps")

    @property
    def vario_valid(self):
        return self.validity("vario")

    @property
    def battery_valid(self):
        return self.validity("battery")

    @property
    def barometer_valid(self):
        return self.validity("barometer")

    @property
    def rpm_valid(self):
        return self.validity("rpm")

    @property
    def temperature_valid(self):
        return self.validity("temperature")

    @property
    def attitude_valid(self):
        return self.validity("attitude")

    @property
    def failsafe_status_valid(self):
        return self.validity("failsafe_status")

    @property
    def inav_status_valid(self):
        return self.validity("inav_status")

    @property
    def navigation_status_valid(self):
        return self.validity("navigation_status")

    @property
    def rc_check_valid(self):
        return self.validity("rc_check")

    @property
    def rc_channel_agreement(self):
        if not self.fc_telemetry_valid or not self.rc_check_valid:
            return None
        for matched in range(RC_CHANNELS_CHECKED + 1):
            percent = (matched * 100 + RC_CHANNELS_CHECKED // 2) // RC_CHANNELS_CHECKED
            if percent == self.rc_accuracy_percent:
                return matched, RC_CHANNELS_CHECKED
        return None

    @property
    def home_data_valid(self):
        return self.validity("home_data")

    @property
    def flex_calibration_valid(self):
        return self.validity("flex_calibration")

    @property
    def primary_control_valid(self):
        return self.state("primary_control_valid")

    @property
    def ground_link_valid(self):
        return self.state("ground_link_valid")

    @property
    def keyboard_packet_valid(self):
        return self.state("keyboard_packet_valid")

    @property
    def left_glove_valid(self):
        return self.state("left_glove_valid")

    @property
    def left_imu_valid(self):
        return self.state("left_imu_valid")

    @property
    def right_imu_valid(self):
        return self.state("right_imu_valid")

    @property
    def glove_orientation_calibrated(self):
        return self.state("glove_orientation_calibrated")

    @property
    def failsafe_active(self):
        return self.state("failsafe_active")

    @property
    def arm_command(self):
        return self.state("arm_command")

    @property
    def rth_command(self):
        return self.state("rth_command")

    @property
    def land_command(self):
        return self.state("land_command")

    @property
    def fc_armed(self):
        return self.state("fc_armed")

    @property
    def arm_state_matches_command(self):
        return self.state("arm_state_matches_command")

    @property
    def rth_active(self):
        return self.state("rth_active")

    @property
    def landing_active(self):
        return self.state("landing_active")

    @property
    def landed(self):
        return self.state("landed")


@dataclass
class TelemetryParserStats:
    packets_parsed: int = 0
    crc_failures: int = 0
    header_failures: int = 0
    sequence_gaps: int = 0
    bytes_discarded: int = 0


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


class BigEndianReader:
    def __init__(self, data, start_index=0):
        self.data = data
        self.index = start_index

    def read_uint8(self):
        value = self.data[self.index]
        self.index += 1
        return value

    def read_uint16(self):
        value = int.from_bytes(
            self.data[self.index:self.index + 2],
            byteorder="big",
            signed=False,
        )
        self.index += 2
        return value

    def read_int16(self):
        value = int.from_bytes(
            self.data[self.index:self.index + 2],
            byteorder="big",
            signed=True,
        )
        self.index += 2
        return value

    def read_uint32(self):
        value = int.from_bytes(
            self.data[self.index:self.index + 4],
            byteorder="big",
            signed=False,
        )
        self.index += 4
        return value

    def read_int32(self):
        value = int.from_bytes(
            self.data[self.index:self.index + 4],
            byteorder="big",
            signed=True,
        )
        self.index += 4
        return value


def parse_telemetry_packet(packet):
    if len(packet) != TELEMETRY_PACKET_LENGTH:
        raise TelemetryParseError(
            f"Expected 113 bytes, received {len(packet)}"
        )

    if packet[0:2] != SYNC_BYTES:
        raise TelemetryParseError("Invalid sync bytes")

    if packet[2] != TELEMETRY_VERSION:
        raise TelemetryParseError(
            f"Invalid telemetry version {packet[2]}"
        )

    if packet[3] != TELEMETRY_MESSAGE_TYPE:
        raise TelemetryParseError(
            f"Invalid message type 0x{packet[3]:02X}"
        )

    payload_length = int.from_bytes(packet[4:6], "big")

    if payload_length != TELEMETRY_PAYLOAD_LENGTH:
        raise TelemetryParseError(
            f"Invalid payload length {payload_length}"
        )

    received_crc = int.from_bytes(packet[111:113], "big")
    calculated_crc = crc16_ccitt_false(packet[2:111])

    if received_crc != calculated_crc:
        raise TelemetryParseError(
            f"Invalid CRC: received 0x{received_crc:04X}, "
            f"calculated 0x{calculated_crc:04X}"
        )

    reader = BigEndianReader(packet, start_index=6)

    sequence = reader.read_uint16()
    timestamp_ms = reader.read_uint32()
    current_mode = reader.read_uint8()
    validity_flags = reader.read_uint16()
    state_flags = reader.read_uint16()

    latitude_e7 = reader.read_int32()
    longitude_e7 = reader.read_int32()
    ground_speed_deci_kph = reader.read_uint16()
    gps_course_centideg = reader.read_uint16()
    gps_altitude_m = reader.read_int32()
    satellite_count = reader.read_uint8()

    vertical_speed_cms = reader.read_int16()

    battery_voltage_deci_v = reader.read_uint16()
    battery_current_deci_a = reader.read_uint16()
    mah_used = reader.read_uint32()
    battery_percent = reader.read_uint8()

    baro_altitude_dm = reader.read_int32()

    motor_rpm = (
        reader.read_int32(),
        reader.read_int32(),
        reader.read_int32(),
        reader.read_int32(),
    )

    esc_temperature_count = reader.read_uint8()
    esc_temperature_deci_c = (
        reader.read_int16(),
        reader.read_int16(),
        reader.read_int16(),
        reader.read_int16(),
    )

    pitch_rad10000 = reader.read_int16()
    roll_rad10000 = reader.read_int16()
    yaw_rad10000 = reader.read_int16()

    cycle_time_us = reader.read_uint16()
    i2c_error_count = reader.read_uint16()
    sensor_status = reader.read_uint16()
    system_load_percent = reader.read_uint16()
    config_profile = reader.read_uint8()
    battery_profile = reader.read_uint8()
    arming_flags = reader.read_uint32()
    active_mode_flags_low = reader.read_uint32()
    active_mode_flags_high = reader.read_uint32()
    mixer_profile = reader.read_uint8()

    nav_mode = reader.read_uint8()
    nav_state = reader.read_uint8()
    nav_error = reader.read_uint8()

    rc_accuracy_percent = reader.read_uint8()
    distance_to_home_m = reader.read_uint16()
    direction_to_home_deg = reader.read_int16()

    if reader.index != 111:
        raise TelemetryParseError(
            f"Decoder stopped at byte {reader.index}, expected byte 111"
        )

    return AirTelemetry(
        raw_packet=bytes(packet),
        sequence=sequence,
        timestamp_ms=timestamp_ms,
        current_mode=current_mode,
        validity_flags=validity_flags,
        state_flags=state_flags,
        latitude_e7=latitude_e7,
        longitude_e7=longitude_e7,
        ground_speed_deci_kph=ground_speed_deci_kph,
        gps_course_centideg=gps_course_centideg,
        gps_altitude_m=gps_altitude_m,
        satellite_count=satellite_count,
        vertical_speed_cms=vertical_speed_cms,
        battery_voltage_deci_v=battery_voltage_deci_v,
        battery_current_deci_a=battery_current_deci_a,
        mah_used=mah_used,
        battery_percent=battery_percent,
        baro_altitude_dm=baro_altitude_dm,
        motor_rpm=motor_rpm,
        esc_temperature_count=esc_temperature_count,
        esc_temperature_deci_c=esc_temperature_deci_c,
        pitch_rad10000=pitch_rad10000,
        roll_rad10000=roll_rad10000,
        yaw_rad10000=yaw_rad10000,
        cycle_time_us=cycle_time_us,
        i2c_error_count=i2c_error_count,
        sensor_status=sensor_status,
        system_load_percent=system_load_percent,
        config_profile=config_profile,
        battery_profile=battery_profile,
        arming_flags=arming_flags,
        active_mode_flags_low=active_mode_flags_low,
        active_mode_flags_high=active_mode_flags_high,
        mixer_profile=mixer_profile,
        nav_mode=nav_mode,
        nav_state=nav_state,
        nav_error=nav_error,
        rc_accuracy_percent=rc_accuracy_percent,
        distance_to_home_m=distance_to_home_m,
        direction_to_home_deg=direction_to_home_deg,
    )



class TelemetryStreamParser:
    def __init__(self):
        self.buffer = bytearray()
        self.stats = TelemetryParserStats()
        self.last_sequence = None
        self.last_packet = None

    def feed(self, received_data):
        self.buffer.extend(received_data)
        completed_packets = []

        while True:
            sync_index = self.buffer.find(SYNC_BYTES)

            if sync_index == -1:
                self._discard_bytes_without_sync()
                break

            if sync_index > 0:
                del self.buffer[:sync_index]
                self.stats.bytes_discarded += sync_index

            if len(self.buffer) < 6:
                break

            message_type = self.buffer[3]
            payload_length = int.from_bytes(self.buffer[4:6], "big")

            if message_type != TELEMETRY_MESSAGE_TYPE or payload_length != TELEMETRY_PAYLOAD_LENGTH:
                self.stats.header_failures += 1
                del self.buffer[0]
                self.stats.bytes_discarded += 1
                continue

            if len(self.buffer) < TELEMETRY_PACKET_LENGTH:
                break

            candidate = bytes(self.buffer[:TELEMETRY_PACKET_LENGTH])

            try:
                packet = parse_telemetry_packet(candidate)
            except TelemetryParseError as error:
                if "CRC" in str(error):
                    self.stats.crc_failures += 1
                else:
                    self.stats.header_failures += 1

                del self.buffer[0]
                self.stats.bytes_discarded += 1
                continue

            del self.buffer[:TELEMETRY_PACKET_LENGTH]
            # A repeated packet is not a new sample or evidence of freshness.
            if candidate == self.last_packet:
                continue
            self.last_packet = candidate
            self._record_sequence(packet.sequence)
            self.stats.packets_parsed += 1

            completed_packets.append(packet)

        return completed_packets

    def _discard_bytes_without_sync(self):
        # Preserve a trailing 0xA5 because the next USB chunk may begin with 0x5A.
        if self.buffer and self.buffer[-1] == SYNC_BYTES[0]:
            discarded_count = len(self.buffer) - 1
            del self.buffer[:-1]
        else:
            discarded_count = len(self.buffer)
            self.buffer.clear()

        self.stats.bytes_discarded += discarded_count

    def _record_sequence(self, sequence):
        if self.last_sequence is not None:
            difference = (sequence - self.last_sequence) & 0xFFFF

            if 1 < difference < 0x8000:
                self.stats.sequence_gaps += difference - 1

        self.last_sequence = sequence


telemetry_parser = TelemetryStreamParser()
latest_telemetry = None
latest_telemetry_received_at = None
latest_telemetry_lock = threading.Lock()


def reset_connection():
    global telemetry_parser, latest_telemetry, latest_telemetry_received_at
    # Called only between serial workers, never while an old reader is running.
    with latest_telemetry_lock:
        telemetry_parser = TelemetryStreamParser()
        latest_telemetry = None
        latest_telemetry_received_at = None


def process_received_data(received_data):
    global latest_telemetry, latest_telemetry_received_at

    completed_packets = telemetry_parser.feed(received_data)

    if not completed_packets:
        return

    for packet in completed_packets:
        with latest_telemetry_lock:
            latest_telemetry = packet
            latest_telemetry_received_at = time.monotonic()


def get_latest_telemetry():
    with latest_telemetry_lock:
        return latest_telemetry


def get_latest_telemetry_age():
    with latest_telemetry_lock:
        if latest_telemetry_received_at is None:
            return float("inf")
        return time.monotonic() - latest_telemetry_received_at


def get_parser_stats():
    return telemetry_parser.stats
