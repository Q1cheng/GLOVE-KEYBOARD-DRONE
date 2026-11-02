"""Nonblocking startup presentation and background-service lifecycle."""

import math
import queue
import threading
import time
import tkinter as tk

from brand_logo import BrandLogo


class BackgroundServices:
    """Each worker owns both start and stop, including a late-returning start."""

    def __init__(self, services):
        self.services = services
        self.errors = queue.Queue()
        self.stopping = threading.Event()
        self.threads = []

    def start(self, services=None):
        for name, service in self.services if services is None else services:
            thread = threading.Thread(target=self._run, args=(name, service),
                                      name=f"startup-{name}", daemon=True)
            self.threads.append(thread)
            thread.start()

    def _run(self, name, service):
        try:
            if not self.stopping.is_set():
                try:
                    service.start()
                except Exception as error:
                    self.errors.put(f"{name}: {error}")
            self.stopping.wait()
        finally:
            try:
                service.stop()
            except Exception as error:
                self.errors.put(f"{name} shutdown: {error}")

    def drain_errors(self, destination):
        while True:
            try:
                destination.append(self.errors.get_nowait())
            except queue.Empty:
                return

    def close(self):
        self.stopping.set()
        deadline = time.monotonic() + 2.5
        for thread in self.threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))


class StartupScreen:
    """A transient cover also covers native WebKit views while they attach."""

    def __init__(self, root):
        self.root = root
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title("Flight Deck Loading")
        self.window.overrideredirect(True)
        self.window.transient(root)
        self.window.configure(bg="#05090C")
        self.canvas = tk.Canvas(self.window, bg="#05090C", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.logo = BrandLogo(self.canvas, 92, "#E8F0F2", "#05090C")
        self.center = (0, 0)
        self.title = self.canvas.create_text(0, 0, text="FLIGHT DECK", fill="#E8F0F2",
                                             font=(".AppleSystemUIFont", 18))
        self.closed = False
        self.started = time.monotonic()
        self.fade_started = None
        self.geometry_binding = root.bind("<Configure>", self._position, add="+")
        self.job = root.after(0, self._show)

    def _position(self, event=None):
        if self.closed or (event is not None and event.widget is not self.root):
            return
        width, height = self.root.winfo_width(), self.root.winfo_height()
        self.window.geometry(f"{width}x{height}+{self.root.winfo_rootx()}+{self.root.winfo_rooty()}")
        self.center = (width/2, height/2-22)
        self.logo.draw(*self.center, angle=(time.monotonic()-self.started)*math.pi/4)
        self.canvas.coords(self.title, width/2, height/2+69)

    def _show(self):
        if self.closed:
            return
        self._position()
        self.window.deiconify()
        self.window.lift()
        self._animate()

    def _animate(self):
        if self.closed:
            return
        now = time.monotonic()
        self.logo.draw(*self.center, angle=(now-self.started)*math.pi/4)
        if self.fade_started is not None:
            progress = min(1, (now-self.fade_started)/.22)
            self.window.attributes("-alpha", 1-progress*progress*(3-2*progress))
            if progress >= 1:
                self.close()
                return
        # Schedule against the next 60 Hz deadline, not 16 ms after rendering.
        elapsed = time.monotonic()-self.started
        next_frame = (math.floor(elapsed*60)+1)/60
        self.job = self.root.after(max(1, round((next_frame-elapsed)*1000)), self._animate)

    def finish(self):
        if not self.closed and self.fade_started is None:
            self.fade_started = time.monotonic()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.root.after_cancel(self.job)
        self.root.unbind("<Configure>", self.geometry_binding)
        self.window.destroy()
