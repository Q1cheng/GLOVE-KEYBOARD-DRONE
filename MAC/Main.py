import os
import queue
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path


def _restart_with_project_python():
    """Keep editor launch buttons on FLIGHT DECK's packaged environment."""
    if getattr(sys, "frozen", False):
        return

    project_python = Path(__file__).resolve().parent / ".venv" / "bin" / "python"
    if not project_python.is_file():
        return

    if os.path.abspath(sys.executable) == os.path.abspath(project_python):
        return

    os.execv(str(project_python), [str(project_python), *sys.argv])


_restart_with_project_python()

from startup import BackgroundServices, StartupScreen


def _request_camera_start(prepared):
    # OpenCV cannot show macOS's first-use permission prompt from its worker.
    import objc
    objc.loadBundle("AVFoundation", {},
                    bundle_path="/System/Library/Frameworks/AVFoundation.framework")
    device = objc.lookUpClass("AVCaptureDevice")
    if device.authorizationStatusForMediaType_("vide") != 0:
        prepared.put(("video", None))
        return
    objc.registerMetaDataForSelector(
        b"AVCaptureDevice", b"requestAccessForMediaType:completionHandler:",
        {"arguments": {3: {"callable": {"retval": {"type": b"v"},
                                       "arguments": {0: {"type": b"^v"},
                                                     1: {"type": b"Z"}}}}}},
    )
    device.requestAccessForMediaType_completionHandler_(
        "vide", lambda granted: prepared.put(("video", None)))


def _prepare_runtime():
    from pynput import keyboard
    import KEYINPUT
    import UI
    import telemetry
    from serial_link import SerialLink
    from video_capture import VideoCapture
    # Import native bridges before the main-thread widget construction steps.
    import attitude_view
    import gps_view

    class StartupKeyboardListener(keyboard.Listener):
        def _run(self):
            from pynput._util.darwin import ListenerMixin
            # Preserve pynput's translation context, acquired on the main queue.
            self._context = self.startup_context
            try:
                ListenerMixin._run(self)
            finally:
                self._context = None

    listener = StartupKeyboardListener(on_press=KEYINPUT.on_key_press,
                                        on_release=KEYINPUT.on_key_release)
    serial_link, video_capture = SerialLink(), VideoCapture()
    services = BackgroundServices((("Keyboard listener", listener),
                                   ("USB serial link", serial_link),
                                   ("Video capture", video_capture)))
    return UI, KEYINPUT, telemetry, serial_link, video_capture, services


def main():
    root = tk.Tk()
    root.title("Flight Deck")
    root.geometry("1600x920")
    root.minsize(1280, 820)
    root.configure(bg="#05090C")
    splash = StartupScreen(root)
    prepared = queue.Queue()
    startup_errors = []
    services = None
    flight_deck = None
    closed = False

    def prepare():
        try:
            prepared.put(("runtime", _prepare_runtime()))
        except Exception:
            prepared.put(("error", traceback.format_exc()))

    def close():
        nonlocal closed
        if closed:
            return
        closed = True
        splash.close()
        if flight_deck is not None:
            flight_deck.close()
        else:
            root.destroy()

    def poll():
        nonlocal services, flight_deck
        if closed:
            return
        while True:
            try:
                kind, result = prepared.get_nowait()
            except queue.Empty:
                break
            if kind == "error":
                print(result)
                close()
                return
            elif kind == "video":
                services.start(services.services[2:])
            else:
                UI, KEYINPUT, telemetry, serial_link, video_capture, services = result
                # Carbon's first keyboard-layout lookup must occur on macOS's main queue.
                from pynput._util.darwin import keycode_context
                with keycode_context() as context:
                    services.services[0][1].startup_context = context
                services.start(services.services[:2])
                try:
                    _request_camera_start(prepared)
                except Exception as error:
                    startup_errors.append(f"Video capture: {error}")
                flight_deck = UI.FlightDeckUI(
                    get_key_mask=KEYINPUT.create_key_mask,
                    get_telemetry=telemetry.get_latest_telemetry,
                    get_telemetry_age=telemetry.get_latest_telemetry_age,
                    get_parser_stats=telemetry.get_parser_stats,
                    video_capture=video_capture, serial_link=serial_link,
                    startup_errors=startup_errors, root=root, on_ready=splash.finish,
                )
                root.protocol("WM_DELETE_WINDOW", close)
        if services is not None:
            services.drain_errors(startup_errors)
        root.after(25, poll)

    root.protocol("WM_DELETE_WINDOW", close)
    root.after(0, poll)
    threading.Thread(target=prepare, name="startup-imports", daemon=True).start()
    try:
        root.mainloop()
    finally:
        if services is not None:
            services.close()


if __name__ == "__main__":
    main()
