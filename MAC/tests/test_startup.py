import threading
import time
import unittest

from startup import BackgroundServices


class Service:
    def __init__(self, gate=None, fail=False):
        self.gate = gate
        self.fail = fail
        self.entered = threading.Event()
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.owner = None

    def start(self):
        self.owner = threading.get_ident()
        self.entered.set()
        if self.gate is not None:
            self.gate.wait()
        if self.fail:
            raise RuntimeError("not connected")
        self.started.set()

    def stop(self):
        assert threading.get_ident() == self.owner
        self.stopped.set()


class StartupTests(unittest.TestCase):
    def test_successful_service_start_and_stop_off_caller_thread(self):
        service = Service()
        runner = BackgroundServices((("USB serial link", service),))
        runner.start()
        self.assertTrue(service.started.wait(1))
        self.assertNotEqual(service.owner, threading.get_ident())
        errors = []
        runner.drain_errors(errors)
        self.assertEqual(errors, [])
        runner.close()
        self.assertTrue(service.stopped.is_set())

    def test_missing_hardware_reports_existing_error_without_blocking(self):
        failed, healthy = Service(fail=True), Service()
        runner = BackgroundServices((("USB serial link", failed), ("Video capture", healthy)))
        runner.start()
        self.assertTrue(healthy.started.wait(1))
        errors = []
        deadline = time.monotonic() + 1
        while not errors and time.monotonic() < deadline:
            runner.drain_errors(errors)
            time.sleep(.005)
        self.assertEqual(errors, ["USB serial link: not connected"])
        runner.close()
        self.assertTrue(failed.stopped.is_set())

    def test_slow_device_does_not_block_other_services_and_stops_if_closed(self):
        gate = threading.Event()
        slow, fast = Service(gate), Service()
        runner = BackgroundServices((("Video capture", slow), ("USB serial link", fast)))
        runner.start()
        self.assertTrue(slow.entered.wait(1))
        self.assertTrue(fast.started.wait(1))
        runner.stopping.set()
        gate.set()
        runner.close()
        self.assertTrue(slow.stopped.is_set())
        self.assertTrue(fast.stopped.is_set())


if __name__ == "__main__":
    unittest.main()
