"""Map presentation state derived exclusively from parsed AirTelemetry objects."""

from collections import deque
import math

TRAIL_MAX_POINTS = 2048
TRAIL_MIN_DISTANCE_M = 1.0
MERCATOR_LATITUDE_LIMIT = 85.05112878


def distance_m(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlon = lat2 - lat1, math.radians(b[1] - a[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, value))))


class GPSState:
    def __init__(self):
        self.history = deque(maxlen=TRAIL_MAX_POINTS)
        self.segment = 0
        self.last_packet = None
        self.interrupted = True

    def update(self, data):
        position = None
        if data and data.gps_valid:
            lat, lon = data.latitude_degrees, data.longitude_degrees
            if (math.isfinite(lat) and math.isfinite(lon)
                    and abs(lat) <= MERCATOR_LATITUDE_LIMIT and abs(lon) <= 180):
                position = [lat, lon]
        if position is None:
            self.interrupted = True
        elif data is not self.last_packet:
            if self.interrupted:
                self.segment += 1
            if (self.interrupted or not self.history
                    or distance_m(self.history[-1][:2], position) >= TRAIL_MIN_DISTANCE_M):
                self.history.append([*position, self.segment])
            self.interrupted = False
        self.last_packet = data

        heading = None
        if data and data.attitude_valid and math.isfinite(data.yaw_radians):
            heading = math.degrees(data.yaw_radians) % 360
        home_valid = bool(data and data.home_data_valid)
        # No home coordinates are provided by this project. Distance/bearing do
        # not establish a verified home pin, and are never used to synthesize one.
        return {
            'position': position,
            'heading': heading,
            'distance': data.distance_to_home_m if home_valid else None,
            'bearing': data.direction_to_home_deg % 360 if home_valid else None,
            'history': list(self.history),
            'segment': self.segment,
        }
