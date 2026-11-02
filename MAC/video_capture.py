import threading
import time
from collections import deque
import cv2

VIDEO_DEVICE_INDEX = 0
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 480


class VideoCapture:
    def __init__(self, device_index=VIDEO_DEVICE_INDEX):
        self.device_index = device_index
        self.capture = None
        self.latest_frame = None
        self.latest_frame_time = None
        self.frame_times = deque(maxlen=30)
        self.frame_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.capture_thread = None
        self.status = "Not started"

    def start(self):
        self.capture = cv2.VideoCapture(
            self.device_index,
            cv2.CAP_AVFOUNDATION,
        )

        if not self.capture.isOpened():
            self.capture.release()
            self.capture = None
            self.status = "Device not found"
            raise RuntimeError(
                f"Could not open video device {self.device_index}. "
                "Check the adapter and try another device index."
            )

        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_WIDTH)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_HEIGHT)
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.stop_event.clear()
        self.status = "Waiting for video frames"

        self.capture_thread = threading.Thread(
            target=self._capture_loop,
            name="video-capture",
            daemon=True,
        )
        self.capture_thread.start()

    def stop(self):
        self.stop_event.set()

        if self.capture_thread is not None:
            self.capture_thread.join(timeout=2.0)
            self.capture_thread = None

        if self.capture is not None:
            self.capture.release()
            self.capture = None

        self.status = "Stopped"

    def get_latest_frame(self):
        with self.frame_lock:
            if self.latest_frame is None:
                return None

            return self.latest_frame.copy()

    def get_latest_frame_info(self):
        with self.frame_lock:
            if self.latest_frame is None:
                return None, None, 0.0
            fps = 0.0
            if len(self.frame_times) > 1:
                duration = self.frame_times[-1] - self.frame_times[0]
                if duration > 0:
                    fps = (len(self.frame_times) - 1) / duration
            return self.latest_frame.copy(), self.latest_frame_time, fps

    def _capture_loop(self):
        while not self.stop_event.is_set():
            success, frame = self.capture.read()

            if not success:
                self.status = "No video frames received"
                time.sleep(0.02)
                continue

            with self.frame_lock:
                self.latest_frame = frame
                self.latest_frame_time = time.monotonic()
                self.frame_times.append(self.latest_frame_time)

            self.status = "Receiving video"
