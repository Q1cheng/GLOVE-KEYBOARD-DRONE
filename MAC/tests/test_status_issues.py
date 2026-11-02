import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from status_issues import IssueTracker
import status_issues


def packet(**changes):
    values = dict(
        sequence=1, current_mode=1, fc_telemetry_valid=True,
        failsafe_status_valid=True, failsafe_active=False,
        primary_control_valid=True, ground_link_valid=True,
        keyboard_packet_valid=True, left_glove_valid=True,
        left_imu_valid=True, right_imu_valid=True,
        glove_orientation_calibrated=True, flex_calibration_valid=True,
        gps_valid=True, vario_valid=True, battery_valid=True,
        barometer_valid=True, rpm_valid=True, temperature_valid=True,
        attitude_valid=True, inav_status_valid=True,
        navigation_status_valid=True, rc_check_valid=True,
        home_data_valid=True, fc_armed=False, arm_command=False,
        arm_state_matches_command=True, battery_percent=75,
        satellite_count=12, rc_accuracy_percent=100, nav_error=0,
        i2c_error_count=0, distance_to_home_m=50,
    )
    values.update(changes)
    return SimpleNamespace(**values)


class IssueTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tracker = IssueTracker()

    def collect(self, data=None, usb=True, video=True, verified=True, now=10):
        return self.tracker.collect(
            packet() if data is None else data, usb, video,
            video_verified=verified, now=now,
        )

    def test_healthy_and_normal_false_flags(self):
        self.assertEqual(self.collect(), ())
        self.assertEqual(self.collect(packet(rth_command=False, land_command=False,
                                             rth_active=False, landing_active=False,
                                             landed=False)), ())

    def test_stale_and_recovered(self):
        self.assertEqual(self.tracker.collect(None, False, False, now=10),
                         ("USB SERIAL UNAVAILABLE", "AIR TELEMETRY UNAVAILABLE",
                          "FPV CAPTURE UNAVAILABLE"))
        self.assertEqual(self.collect(), ())

    def test_failsafe_and_primary_are_first(self):
        issues = self.collect(packet(failsafe_active=True, primary_control_valid=False,
                                     ground_link_valid=False, gps_valid=False))
        self.assertEqual(issues[:2], ("FC FAILSAFE ACTIVE", "PRIMARY CONTROL INVALID"))
        self.assertIn("RIGHT-AIR LINK LOST", issues)
        self.assertEqual(self.collect(packet(sequence=2)), ())

    def test_mode_specific_control(self):
        bad = dict(keyboard_packet_valid=False, left_glove_valid=False,
                   left_imu_valid=False, right_imu_valid=False,
                   glove_orientation_calibrated=False, flex_calibration_valid=False)
        keyboard = self.collect(packet(current_mode=1, **bad))
        self.assertEqual(keyboard, ("KEYBOARD PACKET INVALID",))
        glove = self.collect(packet(current_mode=2, **bad))
        self.assertNotIn("KEYBOARD PACKET INVALID", glove)
        self.assertEqual(len(glove), 5)
        self.assertEqual(self.collect(packet(current_mode=3, **bad)), ())

    def test_parent_fc_failure_suppresses_sensor_flood(self):
        broken = packet(fc_telemetry_valid=False, gps_valid=False,
                        battery_valid=False, rpm_valid=False, nav_error=9)
        self.assertEqual(self.collect(broken), ("FC TELEMETRY UNAVAILABLE",))

    def test_all_validity_flags_and_thresholds(self):
        bad = packet(gps_valid=False, vario_valid=False, battery_valid=False,
                     barometer_valid=False, rpm_valid=False, temperature_valid=False,
                     attitude_valid=False, failsafe_status_valid=False,
                     inav_status_valid=False, navigation_status_valid=False,
                     rc_check_valid=False, home_data_valid=False)
        self.assertEqual(len(self.collect(bad)), 12)
        issues = self.collect(packet(battery_percent=19, satellite_count=5,
                                     rc_accuracy_percent=94, nav_error=2))
        self.assertEqual(issues, ("LOW BATTERY", "GPS FIX DEGRADED",
                                  "RC CHANNEL MATCH LOW", "NAV ERROR: 2"))

    def test_arm_comparison_requires_known_fc_state(self):
        self.assertEqual(self.collect(packet(fc_armed=False, arm_command=True,
                                             arm_state_matches_command=False)),
                         ("ARM STATE MISMATCH",))
        self.assertNotIn("ARM STATE MISMATCH", self.collect(packet(
            inav_status_valid=False, fc_armed=False, arm_command=True,
            arm_state_matches_command=False)))

    def test_i2c_only_recent_increases(self):
        self.assertEqual(self.collect(packet(sequence=1, i2c_error_count=9)), ())
        self.assertEqual(self.collect(packet(sequence=2, i2c_error_count=10), now=11),
                         ("I2C ERRORS INCREASING",))
        self.assertEqual(self.collect(packet(sequence=3, i2c_error_count=10), now=17), ())

    def test_unverified_camera_not_accepted(self):
        self.assertEqual(self.collect(verified=False), ("FPV SOURCE UNVERIFIED",))
        self.assertEqual(self.collect(video=False), ("FPV CAPTURE UNAVAILABLE",))

    def test_optional_home_advisory_is_gated_by_config_and_validity(self):
        previous = status_issues.MAX_HOME_DISTANCE_ADVISORY_M
        try:
            status_issues.MAX_HOME_DISTANCE_ADVISORY_M = 100
            self.assertEqual(self.collect(packet(distance_to_home_m=101)),
                             ("HOME DISTANCE ADVISORY",))
            self.assertNotIn("HOME DISTANCE ADVISORY", self.collect(packet(
                distance_to_home_m=101, home_data_valid=False)))
        finally:
            status_issues.MAX_HOME_DISTANCE_ADVISORY_M = previous


if __name__ == "__main__":
    unittest.main()
