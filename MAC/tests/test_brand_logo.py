import math
import unittest

from brand_logo import logo_paths, transformed_points


class BrandLogoTests(unittest.TestCase):
    def test_contours_fit_the_original_proportions(self):
        self.assertTrue(logo_paths())
        for path in logo_paths():
            self.assertGreaterEqual(len(path['points']), 3)
            for x, y in path['points']:
                self.assertLessEqual(abs(x), .501)
                self.assertLessEqual(abs(y), .501)

    def test_rotation_preserves_geometry(self):
        for path in logo_paths():
            before = transformed_points(path['points'], 92, 100, 100)
            rotated = transformed_points(path['points'], 92, 100, 100, math.pi/2)
            for (x, y), (rx, ry) in zip(before, rotated):
                self.assertAlmostEqual(rx-100, -(y-100))
                self.assertAlmostEqual(ry-100, x-100)

    def test_header_uses_the_same_contours_at_its_existing_size(self):
        for path in logo_paths():
            points = transformed_points(path['points'], 32, 17, 17)
            self.assertTrue(all(0 < value < 34 for point in points for value in point))


if __name__ == '__main__':
    unittest.main()
