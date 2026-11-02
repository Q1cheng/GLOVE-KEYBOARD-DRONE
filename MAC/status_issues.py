import time


LOW_BATTERY_PERCENT = 20  # Matches the existing battery display threshold.
MIN_RC_ACCURACY_PERCENT = 95  # Matches the existing RC accuracy display threshold.
MIN_GPS_SATELLITES = 6  # Display advisory, not a flight-control limit.
I2C_RECENT_ERROR_SECONDS = 5.0
MAX_HOME_DISTANCE_ADVISORY_M = None  # Set a value to enable the advisory.
MAX_HEIGHT_AGL_ADVISORY_M = None  # Requires a verified above-takeoff height source.


class IssueTracker:
    def __init__(self):
        self.last_i2c_count = None
        self.last_i2c_sequence = None
        self.last_i2c_increase_at = None

    def _i2c_issue(self, data, now):
        if not data.fc_telemetry_valid or not data.inav_status_valid:
            self.last_i2c_count = None
            self.last_i2c_sequence = None
            self.last_i2c_increase_at = None
            return False
        if data.sequence != self.last_i2c_sequence:
            count = data.i2c_error_count
            if self.last_i2c_count is not None:
                delta = (count - self.last_i2c_count) & 0xFFFF
                if 0 < delta < 0x8000:
                    self.last_i2c_increase_at = now
            self.last_i2c_count = count
            self.last_i2c_sequence = data.sequence
        return (self.last_i2c_increase_at is not None
                and now - self.last_i2c_increase_at < I2C_RECENT_ERROR_SECONDS)

    def collect(self, data, usb_open, video_live, video_verified=False,
                keyboard_listener_available=True, now=None):
        now = time.monotonic() if now is None else now
        issues = []

        if data is not None:
            if data.fc_telemetry_valid and data.failsafe_status_valid and data.failsafe_active:
                issues.append("FC FAILSAFE ACTIVE")
            if not data.primary_control_valid:
                issues.append("PRIMARY CONTROL INVALID")

        if not usb_open:
            issues.append("USB SERIAL UNAVAILABLE")
        if data is None:
            issues.append("AIR TELEMETRY UNAVAILABLE")
            self.last_i2c_count = None
            self.last_i2c_sequence = None
            self.last_i2c_increase_at = None
        else:
            if not data.ground_link_valid:
                issues.append("RIGHT-AIR LINK LOST")

            if data.current_mode == 1:
                if not keyboard_listener_available:
                    issues.append("KEYBOARD LISTENER UNAVAILABLE")
                if not data.keyboard_packet_valid:
                    issues.append("KEYBOARD PACKET INVALID")
            elif data.current_mode == 2:
                for valid, name in (
                    (data.left_glove_valid, "LEFT GLOVE INVALID"),
                    (data.left_imu_valid, "LEFT IMU INVALID"),
                    (data.right_imu_valid, "RIGHT IMU INVALID"),
                    (data.glove_orientation_calibrated, "GLOVE ORIENTATION UNCALIBRATED"),
                    (data.flex_calibration_valid, "GLOVE FLEX UNCALIBRATED"),
                ):
                    if not valid:
                        issues.append(name)

            if not data.fc_telemetry_valid:
                issues.append("FC TELEMETRY UNAVAILABLE")
                self._i2c_issue(data, now)
            else:
                for valid, name in (
                    (data.gps_valid, "GPS DATA UNAVAILABLE"),
                    (data.vario_valid, "VARIO DATA UNAVAILABLE"),
                    (data.battery_valid, "BATTERY DATA UNAVAILABLE"),
                    (data.barometer_valid, "BAROMETER DATA UNAVAILABLE"),
                    (data.rpm_valid, "MOTOR RPM UNAVAILABLE"),
                    (data.temperature_valid, "ESC TEMPERATURE UNAVAILABLE"),
                    (data.attitude_valid, "ATTITUDE DATA UNAVAILABLE"),
                    (data.failsafe_status_valid, "FAILSAFE STATUS UNAVAILABLE"),
                    (data.inav_status_valid, "INAV STATUS UNAVAILABLE"),
                    (data.navigation_status_valid, "NAV STATUS UNAVAILABLE"),
                    (data.rc_check_valid, "RC CHECK UNAVAILABLE"),
                    (data.home_data_valid, "HOME DATA UNAVAILABLE"),
                ):
                    if not valid:
                        issues.append(name)

                if (data.inav_status_valid and not data.arm_state_matches_command
                        and data.fc_armed != data.arm_command):
                    issues.append("ARM STATE MISMATCH")
                if data.battery_valid and data.battery_percent < LOW_BATTERY_PERCENT:
                    issues.append("LOW BATTERY")
                if data.gps_valid and data.satellite_count < MIN_GPS_SATELLITES:
                    issues.append("GPS FIX DEGRADED")
                if data.rc_check_valid and data.rc_accuracy_percent < MIN_RC_ACCURACY_PERCENT:
                    issues.append("RC CHANNEL MATCH LOW")
                if data.navigation_status_valid and data.nav_error:
                    issues.append(f"NAV ERROR: {data.nav_error}")
                if self._i2c_issue(data, now):
                    issues.append("I2C ERRORS INCREASING")
                if (MAX_HOME_DISTANCE_ADVISORY_M is not None and data.home_data_valid
                        and data.distance_to_home_m > MAX_HOME_DISTANCE_ADVISORY_M):
                    issues.append("HOME DISTANCE ADVISORY")
                height_agl_m = getattr(data, "verified_height_agl_m", None)
                if (MAX_HEIGHT_AGL_ADVISORY_M is not None and height_agl_m is not None
                        and height_agl_m > MAX_HEIGHT_AGL_ADVISORY_M):
                    issues.append("HEIGHT ADVISORY")

        if not video_live:
            issues.append("FPV CAPTURE UNAVAILABLE")
        elif not video_verified:
            issues.append("FPV SOURCE UNVERIFIED")
        return tuple(dict.fromkeys(issues))
