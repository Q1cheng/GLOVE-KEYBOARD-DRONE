import sys
import unittest
from dataclasses import fields, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gps_state import GPSState, TRAIL_MAX_POINTS
from telemetry import AirTelemetry


def packet(**values):
    data = {field.name: 0 for field in fields(AirTelemetry)}
    data.update(raw_packet=b'', motor_rpm=(0,)*4, esc_temperature_deci_c=(0,)*4,
                validity_flags=(1<<1)|(1<<7)|(1<<12), latitude_e7=515010000,
                longitude_e7=-1410000, yaw_rad10000=14661,
                distance_to_home_m=46, direction_to_home_deg=312,
                gps_course_centideg=23000)
    data.update(values)
    return AirTelemetry(**data)


class GPSStateTests(unittest.TestCase):
    def test_parsed_position_heading_and_distinct_home_bearing(self):
        result=GPSState().update(packet())
        self.assertEqual(result['position'],[51.501,-.141])
        self.assertAlmostEqual(result['heading'],84,places=2)
        self.assertEqual(result['bearing'],312)
        self.assertEqual(result['distance'],46)
        self.assertNotIn('home_position',result)

    def test_flags_are_independent_and_course_is_never_heading(self):
        model=GPSState()
        result=model.update(packet(validity_flags=2))
        self.assertIsNotNone(result['position'])
        self.assertIsNone(result['heading'])
        self.assertIsNone(result['distance'])
        result=model.update(packet(validity_flags=(1<<7)|(1<<12)))
        self.assertIsNone(result['position'])
        self.assertIsNotNone(result['heading'])
        self.assertEqual(result['distance'],46)

    def test_stale_reset_breaks_history_instead_of_guessing_a_route(self):
        model=GPSState()
        model.update(packet())
        unavailable=model.update(None)
        self.assertIsNone(unavailable['position'])
        self.assertIsNone(unavailable['heading'])
        self.assertIsNone(unavailable['bearing'])
        result=model.update(packet(latitude_e7=515020000))
        self.assertEqual(len(result['history']),2)
        self.assertNotEqual(result['history'][0][2],result['history'][1][2])

    def test_stationary_dedup_and_exact_live_endpoint(self):
        model=GPSState()
        p=packet()
        model.update(p)
        for i in range(100): model.update(replace(p,sequence=i))
        self.assertEqual(len(model.history),1)
        result=model.update(replace(p,latitude_e7=p.latitude_e7+1))
        self.assertEqual(len(result['history']),1)
        self.assertEqual(result['position'][0],51.5010001)

    def test_history_bounded_and_ordered(self):
        model=GPSState()
        for i in range(TRAIL_MAX_POINTS+10):
            result=model.update(packet(latitude_e7=515010000+i*200))
        self.assertEqual(len(result['history']),TRAIL_MAX_POINTS)
        self.assertLess(result['history'][0][0],result['history'][-1][0])

    def test_coordinates_and_heading_normalization(self):
        model=GPSState()
        self.assertIsNone(model.update(packet(latitude_e7=900000000))['position'])
        self.assertIsNone(model.update(packet(longitude_e7=1810000000))['position'])
        self.assertEqual(model.update(packet(latitude_e7=0,longitude_e7=0))['position'],[0,0])
        self.assertAlmostEqual(model.update(packet(yaw_rad10000=-15708))['heading'],270,places=2)


if __name__=='__main__': unittest.main()
