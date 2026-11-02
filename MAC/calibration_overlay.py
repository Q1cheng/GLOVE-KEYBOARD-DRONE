"""Nonblocking Tk presentation over the dashboard and its native WebKit views."""
import math
import time
import tkinter as tk


class CalibrationOverlay:
    def __init__(self, root, guide, *, background, panel, text, muted, cyan, amber, line, font,
                 anchor_widget=None):
        self.root, self.guide = root, guide
        self.anchor_widget = anchor_widget
        self.background, self.text, self.muted = background, text, muted
        self.cyan, self.amber, self.line, self.font = cyan, amber, line, font
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title("Flight Deck Commands")
        self.window.overrideredirect(True)
        self.window.transient(root)
        self.canvas = tk.Canvas(self.window, bg=background, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.closed = False
        self.visible = False
        self.job = None
        self.last_frame_key = None
        self.transition_started = 0
        self.started = time.monotonic()
        self.geometry = None
        self.binding = root.bind("<Configure>", self._position, add="+")

    def _position(self, event=None):
        if self.closed or not self.visible or (event is not None and event.widget is not self.root):
            return
        width, height = self.root.winfo_width(), self.root.winfo_height()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        banner_width = min(540, width - 32)
        x += (width - banner_width) // 2
        y += 70
        if self.anchor_widget is not None:
            host = self.anchor_widget
            banner_width = min(banner_width, max(1, host.winfo_width() - 24))
            x = host.winfo_rootx() + (host.winfo_width() - banner_width) // 2
            y = host.winfo_rooty() + 10
        width, height = banner_width, 198
        geometry = (width, height, x, y)
        if geometry != self.geometry:
            self.geometry = geometry
            self.window.geometry(f"{width}x{height}+{x}+{y}")

    def sync(self):
        if self.closed:
            return
        active = self.guide.phase != "idle"
        if not active:
            if self.visible:
                self.window.withdraw()
                self.visible = False
                self.last_frame_key = None
            if self.job is not None:
                self.root.after_cancel(self.job)
                self.job = None
            return
        if not self.visible:
            self.visible = True
            self._position()
            self.window.deiconify()
            self.window.lift()
        self._position()
        if self.job is None:
            self._animate()

    def _text(self, x, y, text, size, color, bold=False, width=0):
        return self.canvas.create_text(x, y, text=text, fill=color,
            font=(self.font, size, "bold" if bold else "normal"), width=width, justify="center")

    def _fade(self, color, progress):
        def channels(value):
            return [int(value[i:i+2], 16) for i in (1, 3, 5)]
        return "#" + "".join(f"{round(a + (b-a)*progress):02x}"
                             for a, b in zip(channels(self.background), channels(color)))

    def _animate(self):
        self.job = None
        if self.closed or not self.visible:
            return
        now = time.monotonic()
        frame = self.guide.frame(now)
        key = (frame.phase, frame.stage, frame.title)
        changed = key != self.last_frame_key
        if changed:
            self.transition_started = now
            self.last_frame_key = key
        fade = min(1, (now - self.transition_started) / .12)
        color = self.amber if frame.phase in ("failed", "unavailable") else self.text
        width, height = self.geometry[:2]
        center = width / 2
        self.canvas.delete("all")
        self.canvas.create_rectangle(1, 1, width-1, height-1, outline=self.line)
        self._text(center, 30 if frame.remaining is not None else 67, frame.title,
                   16, self._fade(color, fade), True, width-40)
        if frame.remaining is not None:
            self._text(center, 87, str(frame.remaining), 40, self.cyan)
        self._text(center, 142 if frame.remaining is not None else 112,
                   frame.detail, 11, self.muted, width=width-40)
        bar_y, bar_width = 176, width - 64
        if frame.progress is not None:
            start = center - bar_width / 2
            self.canvas.create_line(start, bar_y, start+bar_width, bar_y, fill=self.line, width=2)
            if frame.progress > 0:
                self.canvas.create_line(start, bar_y, start+bar_width*frame.progress, bar_y,
                                        fill=self.cyan, width=2)
        # Absolute clock keeps the guide aligned if rendering ever misses a frame.
        elapsed = time.monotonic() - self.started
        next_frame = (math.floor(elapsed * 60) + 1) / 60
        self.job = self.root.after(max(1, round((next_frame-elapsed)*1000)), self._animate)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.job is not None:
            self.root.after_cancel(self.job)
        self.root.unbind("<Configure>", self.binding)
        self.window.destroy()
