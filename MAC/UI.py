import base64
import math
import time
import tkinter as tk
from pathlib import Path

import cv2
from status_issues import IssueTracker
from calibration_status import CalibrationStatus
from calibration_guide import CalibrationGuide, CalibrationTransmission
from calibration_overlay import CalibrationOverlay
from command_guide import CommandGuide, CommandTransmission


BACKGROUND = "#05090C"
PANEL = "#081116"
STAGE = "#03080B"
LINE = "#20333C"
TEXT = "#E8F0F2"
MUTED = "#82949D"
DIM = "#51636D"
CYAN = "#4ED4DE"
GREEN = "#43D5A7"
AMBER = "#E9B65E"
RED = "#E27673"
MONO = ".AppleSystemUIFont"
SANS = "Helvetica Neue"
MOTOR_COLORS = (GREEN, AMBER, AMBER, CYAN)
MOTOR_BAR_MAX_RPM = 32000  # Display scale only; not a motor safety limit.


def _photo_from_bgr(image):
    success, png = cv2.imencode(".png", image)
    if not success:
        return None
    return tk.PhotoImage(data=base64.b64encode(png.tobytes()), format="png")


def _draw_satellite_icon(canvas, color, scale=1):
    for points in (
        (11, 4, 14, 1, 17, 4, 14, 7),
        (6, 9, 9, 6, 12, 9, 9, 12),
        (1, 14, 4, 11, 7, 14, 4, 17),
    ):
        canvas.create_polygon(*(point * scale for point in points),
                              fill=color, outline="")
    for x1, y1, x2, y2 in (
        (2, 5, 5, 2), (4, 7, 7, 4),
        (11, 14, 14, 11), (13, 16, 16, 13),
    ):
        canvas.create_line(x1 * scale, y1 * scale, x2 * scale, y2 * scale,
                           fill=color, width=1.8 * scale, capstyle="round")


def _draw_controller_icon(canvas, color, scale=1, stroke=1.7):
    outline = (2, 6, 3, 4.5, 5.5, 4.5, 7, 6, 11, 6, 12.5, 4.5,
               15, 4.5, 16, 6, 17, 12.5, 16, 15, 14, 15.5,
               11, 12, 7, 12, 4, 15.5, 2, 15, 1, 12.5, 2, 6)
    canvas.create_line(*(p * scale for p in outline), fill=color,
                       width=stroke * scale, smooth=True, splinesteps=24,
                       capstyle="round", joinstyle="round")
    for points in ((9, 5.8, 9, 2.5), (4, 8.5, 6.5, 8.5), (5.25, 7.25, 5.25, 9.75)):
        canvas.create_line(*(p * scale for p in points), fill=color,
                           width=stroke * scale, capstyle="round")
    for x, y in ((12.75, 7.3), (11.55, 8.5), (13.95, 8.5), (12.75, 9.7)):
        canvas.create_oval((x-.55)*scale, (y-.55)*scale,
                           (x+.55)*scale, (y+.55)*scale, fill=color, outline="")


def _draw_brand_logo(canvas, color, background, size):
    from brand_logo import BrandLogo
    canvas.brand_logo = BrandLogo(canvas, size - 2, color, background)
    canvas.brand_logo.draw(size / 2, size / 2)


def _draw_compact_satellite_icon(canvas, color, scale=1):
    for points in (
        (1, 13, 5, 17, 8, 14, 4, 10),
        (10, 4, 14, 1, 17, 4, 13, 8),
    ):
        canvas.create_polygon(*(point * scale for point in points),
                              fill=color, outline="")
    canvas.create_line(7 * scale, 11 * scale, 8 * scale, 10 * scale,
                       fill=color, width=1.5 * scale)
    canvas.create_line(10 * scale, 8 * scale, 11 * scale, 7 * scale,
                       fill=color, width=1.5 * scale)
    canvas.create_oval(7 * scale, 7 * scale, 11 * scale, 11 * scale,
                       fill=color, outline="")
    canvas.create_line(11 * scale, 10 * scale, 14 * scale, 13 * scale,
                       fill=color, width=1.2 * scale)
    canvas.create_oval(13.5 * scale, 12.5 * scale, 15.5 * scale, 14.5 * scale,
                       fill=color, outline="")


def _draw_link_icon(canvas, color, scale=1, stroke=1.5):
    for bounds, start in (((1.5, 5, 9.5, 13), 90), ((8.5, 5, 16.5, 13), 270)):
        canvas.create_arc(*(point * scale for point in bounds),
                          start=start, extent=180, style="arc",
                          outline=color, width=stroke * scale)
    for points in ((5.5, 5, 7.5, 5), (5.5, 13, 7.5, 13),
                   (10.5, 5, 12.5, 5), (10.5, 13, 12.5, 13),
                   (6.5, 9, 11.5, 9)):
        canvas.create_line(*(point * scale for point in points),
                           fill=color, width=stroke * scale, capstyle="round")


def _draw_wifi_icon(canvas, color, scale=1, stroke=1.5):
    # Both arcs share the dot's center, so the symbol stays circular at every size.
    for radius in (10, 6):
        bounds = (9 - radius, 13.5 - radius, 9 + radius, 13.5 + radius)
        canvas.create_arc(*(point * scale for point in bounds),
                          start=45, extent=90, style="arc",
                          outline=color, width=stroke * scale)
    canvas.create_oval(8.1 * scale, 12.6 * scale, 9.9 * scale, 14.4 * scale,
                       fill=color, outline="")


class FlightDeckUI:
    def __init__(
        self,
        get_key_mask,
        get_telemetry,
        get_telemetry_age,
        get_parser_stats,
        video_capture,
        serial_link,
        startup_errors,
        root=None,
        on_ready=None,
    ):
        self.get_key_mask = get_key_mask
        self.get_telemetry = get_telemetry
        self.get_telemetry_age = get_telemetry_age
        self.get_parser_stats = get_parser_stats
        self.video_capture = video_capture
        self.serial_link = serial_link
        self.startup_errors = startup_errors
        self.root = root if root is not None else tk.Tk()
        self.root.title("Flight Deck")
        self.root.geometry("1600x920")
        self.root.minsize(1280, 820)
        self.root.configure(bg=BACKGROUND)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.video_photo = None
        self.last_video_time = None
        self.last_video_size = None
        self.video_fps = 0.0
        self.telemetry_hz = 0.0
        self.last_rate_check = time.monotonic()
        self.last_packet_count = 0
        self.last_warnings = None
        self.issue_tracker = IssueTracker()
        self.calibration_status = CalibrationStatus()
        self.calibration_guide = CalibrationGuide()
        self.calibration_overlay = None
        self.calibration_transmission = CalibrationTransmission()
        self.command_guide = CommandGuide()

        self.closed = False
        if on_ready is None:
            self._build_header()
            self._build_dashboard()
            self.root.after(50, self._update)
        else:
            self.root.after(1, lambda: self._initialize_dashboard(on_ready))

    def _initialize_dashboard(self, on_ready):
        if self.closed:
            return
        self._build_header()
        self._build_dashboard(on_ready)

    def _panel(self, parent):
        return tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1)

    def _label(self, parent, text, size=10, color=TEXT, bold=False, bg=PANEL):
        return tk.Label(
            parent,
            text=text,
            bg=bg,
            fg=color,
            font=(MONO, size, "bold" if bold else "normal"),
            anchor="w",
        )

    def _divider(self, parent, padding=2):
        tk.Frame(parent, bg=LINE, height=1).pack(fill="x", padx=12, pady=padding)

    def _section(self, parent, title, icon_name=None):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=12, pady=(3, 1))
        if icon_name:
            self._icon(row, icon_name, CYAN, size=14).pack(side="left", padx=(0, 6))
        self._label(row, title, 10, MUTED, True).pack(side="left")

    def _icon(self, parent, kind, color=MUTED, size=18, bg=PANEL):
        icon = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0)
        s = size / 18

        def line(*points, width=1.7):
            icon.create_line(*(point * s for point in points), fill=color, width=width * s,
                             capstyle="round", joinstyle="round")

        def rect(x1, y1, x2, y2, fill=""):
            icon.create_rectangle(x1 * s, y1 * s, x2 * s, y2 * s,
                                  outline=color, fill=fill, width=1.5 * s)

        def oval(x1, y1, x2, y2, fill=""):
            icon.create_oval(x1 * s, y1 * s, x2 * s, y2 * s,
                             outline=color, fill=fill, width=1.5 * s)

        if kind == "drone":
            _draw_brand_logo(icon, color, bg, size)
        elif kind == "battery":
            rect(5, 4, 13, 16)
            icon.create_rectangle(7*s, 2*s, 11*s, 4*s, fill=color, outline="")
            icon.create_rectangle(6.5*s, 14.5*s, 11.5*s, 14.5*s,
                                  fill=GREEN, outline="", state="hidden", tags="charge")
        elif kind == "altitude":
            line(3, 15, 15, 15)
            line(5, 12, 13, 12)
            line(7, 9, 11, 9)
            line(9, 9, 9, 2)
            line(6, 5, 9, 2, 12, 5)
        elif kind == "speed":
            icon.create_arc(2 * s, 3 * s, 16 * s, 17 * s, start=-25, extent=230,
                            outline=color, width=1.7 * s, style="arc")
            line(9, 10, 9, 5.5, width=1.5)
            icon.create_oval(7.9*s, 8.9*s, 10.1*s, 11.1*s, fill=color, outline="")
        elif kind == "gps":
            _draw_satellite_icon(icon, color, s)
        elif kind == "summary_gps":
            _draw_satellite_icon(icon, color, s * 0.83)
            icon.move("all", size * 0.085, size * 0.085)
        elif kind == "home":
            line(1.5, 7.5, 9, 2, 16.5, 7.5, width=2)
            icon.create_rectangle(11.5*s, 1.5*s, 15*s, 6*s, fill=color, outline="")
            icon.create_polygon(*(p*s for p in (3, 8, 9, 4, 15, 8, 15, 16,
                                                9, 16, 9, 10.5, 5.5, 10.5,
                                                5.5, 16, 3, 16)), fill=color, outline="")
            icon.create_rectangle(10.5*s, 10.5*s, 13.5*s, 13.5*s, fill=bg, outline="")
        elif kind == "usb":
            line(9, 15, 9, 4)
            line(9, 11, 4, 8, 4, 5)
            line(9, 8, 14, 5)
            line(7, 4, 9, 2, 11, 4)
            rect(13, 3, 15, 5, fill=color)
            oval(3, 4, 5, 6, fill=color)
            rect(7, 14, 11, 16)
        elif kind == "link":
            _draw_link_icon(icon, color, s)
        elif kind == "radio":
            _draw_wifi_icon(icon, color, s * 16 / 18, stroke=1.7 * 18 / 16)
            icon.move("all", s, s)
        elif kind == "keyboard":
            line(3, 4, 15, 4)
            line(3, 14, 15, 14)
            line(1, 6, 1, 12)
            line(17, 6, 17, 12)
            for x, y, start in ((1, 4, 90), (13, 4, 0), (1, 10, 180), (13, 10, 270)):
                icon.create_arc(x*s, y*s, (x+4)*s, (y+4)*s,
                                start=start, extent=90, style="arc",
                                outline=color, width=1.7*s)
            for y in (6.5, 9):
                for x in (4, 6.5, 9, 11.5, 14):
                    icon.create_rectangle((x-.6)*s, (y-.6)*s, (x+.6)*s, (y+.6)*s,
                                          fill=color, outline="")
            for x1, x2 in ((3.4, 4.6), (6, 12), (13.4, 14.6)):
                icon.create_rectangle(x1*s, 10.9*s, x2*s, 12.1*s, fill=color, outline="")
        elif kind == "shield":
            line(9, 2, 15, 4, 14, 12, 9, 16, 4, 12, 3, 4, 9, 2)
        elif kind == "pulse":
            line(1, 9, 5, 9, 7, 4, 10, 14, 12, 8, 17, 8)
        elif kind == "quality_pulse":
            line(1, 9, 5, 9, 7, 4, 10, 14, 12, 8, 17, 8, width=2.4)
        elif kind == "camera":
            line(3, 5, 6, 5, 7.2, 2.7, 10.8, 2.7, 12, 5, 15, 5, width=1.5)
            line(1, 7, 1, 13, width=1.5)
            line(17, 7, 17, 13, width=1.5)
            line(3, 15, 15, 15, width=1.5)
            for x, y, start in ((1, 5, 90), (13, 5, 0), (1, 11, 180), (13, 11, 270)):
                icon.create_arc(x*s, y*s, (x+4)*s, (y+4)*s,
                                start=start, extent=90, style="arc",
                                outline=color, width=1.5*s)
            oval(5.5, 6.5, 12.5, 13.5)
            line(3, 4.2, 4.8, 4.2, width=1.5)
            for x in (3.5, 14.5):
                icon.create_oval((x-.45)*s, 6.7*s, (x+.45)*s, 7.6*s,
                                 fill=color, outline="")
        elif kind == "control":
            _draw_controller_icon(icon, color, s)
        elif kind == "glove":
            line(4, 16, 3, 12, 2, 10, 3, 9, 4, 9, 6, 11, 6, 3, 7, 2, 8, 3, 8, 9)
            line(8, 9, 8, 2, 9, 1, 10, 2, 10, 9)
            line(10, 9, 10, 3, 11, 2, 12, 3, 12, 9)
            line(12, 9, 12, 5, 13, 4, 14, 5, 14, 12, 12, 16, 4, 16)
        elif kind == "imu":
            oval(3, 3, 15, 15)
            oval(7, 7, 11, 11)
            line(9, 1, 9, 4)
            line(9, 14, 9, 17)
            line(1, 9, 4, 9)
            line(14, 9, 17, 9)
        elif kind == "barometer":
            line(4, 15, 4, 4, 14, 4, 14, 15)
            line(7, 12, 11, 12)
            line(7, 9, 12, 9)
            line(7, 6, 10, 6)
        elif kind == "attitude":
            line(9, 2.5, 9, 15.5, width=1.5)
            line(2, 10.5, 9, 6.5, 16, 10.5, width=1.5)
            line(6, 15, 9, 13, 12, 15, width=1.5)
        elif kind == "chip":
            rect(4, 4, 14, 14)
            for p in (6, 9, 12):
                line(p, 2, p, 4)
                line(p, 14, p, 16)
                line(2, p, 4, p)
                line(14, p, 16, p)
        elif kind == "signal":
            bar_width = 2
            gap = 1
            left = (size - (4 * bar_width + 3 * gap)) / 2
            for index, top in enumerate((12, 9, 6, 3)):
                x = left + index * (bar_width + gap)
                icon.create_rectangle(x, top * s, x + bar_width, 16 * s,
                                      fill=color, outline="")
        elif kind == "packet_signal":
            for x, top in ((1, 11), (5, 8), (9, 5), (13, 2)):
                icon.create_rectangle(x, top, x + 2, 15, fill=color, outline="")
        elif kind == "document":
            line(4, 2, 12, 2, 15, 5, 15, 16, 4, 16, 4, 2)
            line(12, 2, 12, 5, 15, 5)
            line(6, 9, 13, 9)
            line(6, 12, 12, 12)
        elif kind == "warning":
            line(9, 2, 17, 16, 1, 16, 9, 2)
            line(9, 6.5, 9, 10.25, width=1.5)
            icon.create_oval(8.25*s, 12.25*s, 9.75*s, 13.75*s,
                             fill=color, outline="")
        return icon

    def _build_header(self):
        header = tk.Frame(self.root, bg=BACKGROUND, height=50)
        header.pack(fill="x")
        header.pack_propagate(False)
        header.grid_columnconfigure(0, weight=2)
        for column in range(1, 7):
            header.grid_columnconfigure(column, weight=1)
        header.grid_rowconfigure(0, weight=1)

        brand = tk.Frame(header, bg=BACKGROUND)
        brand.grid(row=0, column=0, sticky="w", padx=(18, 8), pady=8)
        self._icon(brand, "drone", TEXT, size=34, bg=BACKGROUND).pack(side="left", padx=(0, 24))
        wordmark_box = tk.Frame(brand, bg=BACKGROUND)
        wordmark = tk.Label(
            wordmark_box, text="F L I G H T   D E C K", bg=BACKGROUND, fg=TEXT,
            font=(SANS, 15),
        )
        # Keep the approved wordmark allocation when selecting the shared family.
        wordmark_box.configure(width=wordmark.winfo_reqwidth(), height=wordmark.winfo_reqheight())
        wordmark_box.pack(side="left")
        wordmark.destroy()
        wordmark = tk.Canvas(wordmark_box, bg=BACKGROUND, highlightthickness=0)
        wordmark.place(x=0, y=0, relwidth=1, relheight=1)
        title_font = (MONO, 15)
        title_width = int(wordmark.tk.call("font", "measure", title_font, "F L I G H T   D E C K"))
        title_x = (int(wordmark_box.cget("width")) - title_width) / 2
        title_y = int(wordmark_box.cget("height")) / 2
        wordmark.create_text(title_x, title_y, text="F L I G H T   ",
                             font=title_font, fill=TEXT, anchor="w")
        deck_x = title_x + int(wordmark.tk.call("font", "measure", title_font, "F L I G H T   "))
        wordmark.create_text(deck_x, title_y, text="D E C K",
                             font=(MONO, 15, "bold"), fill=TEXT, anchor="w")

        header_specs = (
            ("usb", "MAC \u2194 RIGHT USB SERIAL", "link", CYAN, 1),
            ("air", "RIGHT \u2192 AIR ESP-NOW", "radio", CYAN, 2),
            ("mode", "MODE --", "keyboard", TEXT, 3),
            ("arm", "ARM --", "shield", AMBER, 4),
            ("telemetry", "TELEMETRY --", "pulse", CYAN, 5),
            ("camera", "CAMERA --", "camera", TEXT, 6),
        )
        self.header_labels = {}
        for name, caption, icon_name, color, column in header_specs:
            cell = tk.Frame(header, bg=BACKGROUND)
            cell.grid(row=0, column=column, sticky="nsew", pady=12)
            tk.Frame(cell, bg=LINE, width=1).pack(side="left", fill="y", padx=(0, 10))
            self._icon(cell, icon_name, color, bg=BACKGROUND).pack(side="left", padx=(0, 7))
            label = tk.Label(
                cell, text=caption, bg=BACKGROUND, fg=MUTED,
                font=(MONO, 10, "bold"), anchor="w",
            )
            label.pack(side="left", fill="x", expand=True)
            self.header_labels[name] = label
        tk.Frame(self.root, bg=LINE, height=1).pack(fill="x")

    def _build_dashboard(self, on_ready=None):
        body = tk.Frame(self.root, bg=BACKGROUND)
        body.pack(fill="both", expand=True, padx=(10, 19), pady=(9, 12))

        builders = (self._build_sidebar, self._build_video, self._build_right_column,
                    self._build_motors, self._build_warnings)
        if on_ready is None:
            for builder in builders:
                builder(body)
            return
        steps = iter(builders)

        def build_next():
            if self.closed:
                return
            builder = next(steps, None)
            if builder is None:
                self._update()
                self.root.after_idle(on_ready)
                return
            builder(body)
            self.root.after(1, build_next)

        self.root.after(1, build_next)

    def _metric(self, parent, name, icon_name):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=12)
        metric_icon = self._icon(row, icon_name, TEXT, size=22)
        metric_icon.pack(side="left", padx=(1, 10))
        content = tk.Frame(row, bg=PANEL)
        content.pack(side="left", fill="x", expand=True)
        self._label(content, name, 10, MUTED, True).pack(fill="x")
        values = tk.Frame(content, bg=PANEL)
        values.pack(fill="x")
        value = self._label(values, "--", 17, TEXT)
        value.pack(side="left")
        if name == "BATTERY":
            self.battery_icon = metric_icon
            self.battery_percent_label = self._label(values, "--", 17, TEXT)
            self.battery_percent_label.pack(side="right")
            self.battery_bar = tk.Canvas(
                content, width=1, height=5, bg=LINE, highlightthickness=0,
            )
            self.battery_bar.pack(fill="x", pady=(3, 0))
            self.battery_fill = self.battery_bar.create_rectangle(
                0, 0, 0, 5, fill=GREEN, outline="",
            )
        return value

    def _status_row(self, parent, name, icon_name):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=12)
        icon = self._sensor_icon(row, "cycle_chip") if name == "FC CYCLE" else self._icon(
            row, icon_name, MUTED, size=16)
        icon.pack(side="left", padx=(1, 8))
        self._label(row, name, 10, MUTED).pack(side="left")
        value = self._label(row, "--", 9 if name == "RC CHANNEL MATCH" else 10, DIM, True)
        value.pack(side="right")
        return value

    def _sensor_icon(self, parent, kind):
        icon = tk.Canvas(parent, width=16, height=16, bg=PANEL,
                         highlightthickness=0, borderwidth=0)

        def line(*points):
            icon.create_line(*points, fill=MUTED, width=1.25,
                             capstyle="round", joinstyle="round")

        def oval(*bounds):
            icon.create_oval(*bounds, outline=MUTED, width=1.25)

        if kind == "link":
            _draw_link_icon(icon, MUTED, stroke=1.25)
        elif kind == "radio":
            _draw_wifi_icon(icon, MUTED, stroke=1.25)
        elif kind == "control":
            _draw_controller_icon(icon, MUTED, stroke=1.25)
        elif kind == "glove":
            for x, top in ((5, 3), (7, 1.5), (9, 2.5), (11, 4.5)):
                icon.create_arc(x, top, x + 2, top + 2, start=0, extent=180,
                                style="arc", outline=MUTED, width=1.25)
            line(5, 4, 5, 10.5, 3.5, 8.5, 2.5, 8.5, 1.5, 9.5,
                 2, 11, 4, 14, 6, 16, 11, 16, 13, 13, 13, 5.5)
            line(7, 2.5, 7, 8.5)
            line(9, 2.5, 9, 8.5)
            line(11, 3.5, 11, 9)
        elif kind == "imu":
            oval(2.5, 2.5, 15.5, 15.5)
            oval(3.7, 7.4, 14.3, 10.6)
            icon.create_oval(7.4, 3.7, 10.6, 14.3, fill=PANEL, outline=MUTED, width=1.25)
            icon.create_oval(8.35, 8.35, 9.65, 9.65, fill=MUTED, outline="")
            for tick in ((9, .5, 9, 1), (9, 17, 9, 17.5),
                         (.5, 9, 1, 9), (17, 9, 17.5, 9)):
                line(*tick)
        elif kind == "gps":
            _draw_satellite_icon(icon, MUTED)
        elif kind == "battery":
            icon.create_rectangle(5, 4, 13, 16, outline=MUTED, width=1.25)
            icon.create_rectangle(7, 2, 11, 4, fill=MUTED, outline="")
        elif kind == "barometer":
            icon.create_arc(1, 1, 17, 17, start=-30, extent=240,
                            style="arc", outline=MUTED, width=1.25)
            for tick in ((3, 9, 4, 9), (4, 5.5, 4.9, 6),
                         (6, 3.5, 6.5, 4.4), (9, 2.7, 9, 3.7),
                         (12, 3.5, 11.5, 4.4), (14, 5.5, 13.1, 6),
                         (15, 9, 14, 9)):
                line(*tick)
            line(8, 13, 9, 5.5, 10, 13)
            icon.create_arc(7.5, 12.5, 10.5, 15.5, start=135, extent=270,
                            style="arc", outline=MUTED, width=1.25)
        elif kind == "attitude":
            line(9, 2.5, 9, 15.5)
            line(2, 10.5, 9, 6.5, 16, 10.5)
            line(6, 15, 9, 13, 12, 15)
        elif kind == "chip":
            icon.create_rectangle(4, 4, 14, 14, outline=MUTED, width=1.25)
            for p in (6, 9, 12):
                line(p, 1, p, 4)
                line(p, 14, p, 17)
                line(1, p, 4, p)
                line(14, p, 17, p)
        elif kind == "cycle_chip":
            icon.create_rectangle(4, 4, 14, 14, outline=MUTED, width=1.25)
            for p in (6, 9, 12):
                line(p, 2, p, 4)
                line(p, 14, p, 16)
                line(2, p, 4, p)
                line(14, p, 16, p)
            icon.itemconfigure("all", width=1.6)
        elif kind == "calibration":
            for x, knob in ((4, 6), (9, 12), (14, 6)):
                line(x, 2, x, knob - 2)
                line(x, knob + 2, x, 16)
                oval(x - 2, knob - 2, x + 2, knob + 2)
        icon.scale("all", 0, 0, 16 / 18, 16 / 18)
        return icon

    def _sensor_row(self, parent, title, icon_name):
        row = tk.Frame(parent, bg=PANEL, height=18)
        row.pack(fill="x", padx=12)
        row.pack_propagate(False)
        self._sensor_icon(row, icon_name).place(x=0, y=1)
        label = self._label(row, title, 8 if title == "MAC \u2194 RIGHT USB SERIAL" else 9, MUTED)
        label.place(x=28, y=0)
        if title in ("MAC \u2194 RIGHT USB SERIAL", "RIGHT \u2192 AIR ESP-NOW"):
            row.bind("<Configure>", lambda event, text=label: text.configure(
                font=(MONO, 7 if event.width < 185 else
                      8 if text.cget("text") == "MAC \u2194 RIGHT USB SERIAL" else 9)
            ))
        value = self._label(row, "--", 9, DIM, True)
        value.configure(width=7, anchor="e")
        value.place(relx=1, y=0, anchor="ne")
        return value

    def _build_sidebar(self, body):
        sidebar = self._panel(body)
        sidebar.place(relx=0, rely=0, relwidth=0.156, relheight=1)

        metrics = tk.Frame(sidebar, bg=PANEL)
        metrics.pack(fill="x", pady=(4, 0))
        self.metric_labels = {}
        for key, title, icon_name in (
            ("battery", "BATTERY", "battery"),
            ("altitude", "BARO ALTITUDE", "altitude"),
            ("speed", "GROUND SPEED", "speed"),
            ("gps", "GPS", "summary_gps"),
            ("home", "HOME DISTANCE", "home"),
        ):
            self.metric_labels[key] = self._metric(metrics, title, icon_name)
            if key != "home":
                self._divider(metrics, padding=1)

        self._divider(sidebar)
        self._section(sidebar, "LINK & SENSORS", "signal")
        self.sensor_labels = {}
        for name, title, icon_name in (
            ("MAC <> RIGHT USB", "MAC \u2194 RIGHT USB SERIAL", "link"),
            ("RIGHT -> AIR ESP-NOW", "RIGHT \u2192 AIR ESP-NOW", "radio"),
            ("PRIMARY CONTROL", "PRIMARY CONTROL", "control"),
            ("LEFT GLOVE", "LEFT GLOVE", "glove"),
            ("LEFT IMU", "LEFT IMU", "imu"),
            ("RIGHT IMU", "RIGHT IMU", "imu"),
            ("GPS DATA", "GPS", "gps"),
            ("BATTERY DATA", "BATTERY", "battery"),
            ("BAROMETER", "BAROMETER", "barometer"),
            ("ATTITUDE", "ATTITUDE", "attitude"),
            ("FC TELEMETRY", "FC TELEMETRY", "chip"),
        ):
            self.sensor_labels[name] = self._sensor_row(sidebar, title, icon_name)
            if name == "RIGHT IMU":
                row = tk.Frame(sidebar, bg=PANEL, height=18)
                row.pack(fill="x", padx=12)
                row.pack_propagate(False)
                self._sensor_icon(row, "calibration").place(x=0, y=1)
                self._label(row, "GLOVE CAL.", 8, MUTED).place(x=28, y=1)
                self.calibration_label = self._label(row, "UNAVAILABLE", 8, DIM, True)
                self.calibration_label.configure(width=16, anchor="e")
                self.calibration_label.place(relx=1, y=1, anchor="ne")

        self._divider(sidebar)
        self._section(sidebar, "SESSION QUALITY", "quality_pulse")
        self.quality_labels = {}
        for name, icon_name in (
            ("PACKET RETENTION", "packet_signal"), ("SEQUENCES SKIPPED", "document"),
            ("RC CHANNEL MATCH", "control"), ("FC CYCLE", "chip"),
        ):
            self.quality_labels[name] = self._status_row(sidebar, name, icon_name)

        legend = tk.Frame(sidebar, bg=PANEL)
        legend.pack(side="bottom", fill="x", pady=(0, 4))
        self._divider(legend)
        heading = tk.Frame(legend, bg=PANEL, height=20)
        heading.pack(fill="x")
        heading.pack_propagate(False)
        self._label(heading, "KEYBOARD LEGEND", 10, MUTED, True).pack(
            side="left", padx=(12, 0),
        )
        display_only = self._label(heading, "(DISPLAY ONLY)", 10, MUTED)
        display_only.configure(padx=0)
        display_only.pack(side="left")

        def keycap(parent, caption, width=21):
            height = 17
            cap = tk.Canvas(parent, width=width, height=height, bg=PANEL,
                            highlightthickness=0, borderwidth=0)
            cap.create_polygon(
                3, 1, width - 4, 1, width - 2, 3, width - 2, height - 4,
                width - 4, height - 2, 3, height - 2, 1, height - 4, 1, 3,
                fill=STAGE, outline=DIM, width=1,
            )
            cap.create_text(width / 2, height / 2, text=caption, fill=TEXT,
                            font=(MONO, 8, "bold"))
            return cap

        bindings = (
            (("W", "S"), "PITCH", "\u2318\u21e7L", "LAND"),
            (("A", "D"), "ROLL", "B", "BUZZER"),
            (("\u2191", "\u2193"), "THROTTLE", "\u2318\u21e71", "KEYBOARD"),
            (("\u2190", "\u2192"), "YAW", "\u2318\u21e72", "GLOVE"),
            (("\u2318\u21e7ESC",), "RTH", "\u2318\u21e73", "ELRS"),
        )
        for left_keys, left_action, right_key, right_action in bindings:
            row = tk.Frame(legend, bg=PANEL, height=20)
            row.pack(fill="x", padx=10)
            row.pack_propagate(False)
            left = tk.Frame(row, bg=PANEL)
            left.place(relx=0, rely=0, relwidth=0.57, relheight=1)
            right = tk.Frame(row, bg=PANEL)
            right.place(relx=0.57, rely=0, relwidth=0.43, relheight=1)
            for index, caption in enumerate(left_keys):
                keycap(left, caption, 52 if caption.endswith("ESC") else 21).place(x=index * 24, y=1)
            left_label = self._label(left, left_action, 8, MUTED)
            left_label.place(x=58, y=2)
            left.bind("<Configure>", lambda event, label=left_label: label.place_configure(
                x=min(58, max(0, event.width - label.winfo_reqwidth()))
            ))
            keycap(right, right_key, width=32).place(x=0, y=1)
            right_label = self._label(right, right_action, 8, MUTED)
            right_label.place(x=37, y=2)
            right.bind("<Configure>", lambda event, label=right_label: label.place_configure(
                x=min(37, max(0, event.width - label.winfo_reqwidth()))
            ))

        for key, action in (("CMD+SHIFT+A", "ARM"), ("CMD+SHIFT+D", "DISARM")):
            row = tk.Frame(legend, bg=PANEL, height=20)
            row.pack(fill="x", padx=10)
            row.pack_propagate(False)
            keycap(row, key, width=86).place(x=0, y=1)
            self._label(row, action, 8, MUTED).place(x=94, y=2)

        row = tk.Frame(legend, bg=PANEL, height=20)
        row.pack(fill="x", padx=10)
        row.pack_propagate(False)
        for index, caption in enumerate(("1", "2", "3")):
            keycap(row, caption).place(x=index * 31, y=1)
            if index < 2:
                self._label(row, "+", 8, MUTED).place(x=index * 31 + 21, y=2)
        self._label(row, "CALIBRATE (3s)", 8, MUTED).place(x=94, y=2)

    def _build_video(self, body):
        panel = self._panel(body)
        panel.place(relx=0.162, rely=0, relwidth=0.508, relheight=0.885)
        stage = tk.Frame(panel, bg=STAGE)
        stage.pack(fill="both", expand=True, padx=2, pady=2)
        self.video_canvas = tk.Canvas(stage, bg=STAGE, highlightthickness=0)
        self.video_canvas.pack(fill="both", expand=True)
        self.video_placeholder = self.video_canvas.create_text(
            0, 0, text="NO VIDEO SIGNAL", fill=MUTED, font=(MONO, 13, "bold"),
        )
        self.video_canvas.bind("<Configure>", self._resize_video)
        self.video_info = tk.Label(
            stage, text="FPV VIDEO  |  NO SIGNAL", bg="#0A151B", fg=TEXT,
            font=(MONO, 10, "bold"), padx=10, pady=5,
        )
        self.video_info.place(x=9, y=9)
        self.video_battery = tk.Label(
            stage, text="", bg="#0A151B", fg=TEXT,
            font=(MONO, 15, "bold"), padx=9, pady=4,
        )
        self.video_battery.place(x=9, rely=1, y=-9, anchor="sw")

    def _build_right_column(self, body):
        right = tk.Frame(body, bg=BACKGROUND)
        right.place(relx=0.676, rely=0, relwidth=0.324, relheight=0.885)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=47, uniform="right_views")
        right.grid_rowconfigure(1, weight=53, uniform="right_views")

        model = self._panel(right)
        model.grid(row=0, column=0, sticky="nsew", pady=(0, 4))
        heading = tk.Frame(model, bg=PANEL)
        heading.pack(fill="x", padx=12, pady=(3, 1))
        self._icon(heading, "attitude", CYAN, size=14).pack(side="left", padx=(0, 6))
        self._label(heading, "ATTITUDE / 3D MODEL", 11, TEXT).pack(side="left")
        model_content = tk.Frame(model, bg=PANEL)
        model_content.pack(fill="both", expand=True, padx=(0, 10), pady=(8, 0))
        from attitude_view import AttitudeView
        self.attitude_view = AttitudeView(model_content)

        gps = self._panel(right)
        gps.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.map_area = tk.Frame(gps, bg=STAGE, width=1, height=1)
        self.map_area.pack(fill="both", expand=True)
        from gps_view import GPSView
        self.gps_view = GPSView(self.map_area)


    def _build_motors(self, body):
        panel = self._panel(body)
        panel.place(relx=0.162, rely=0.895, relwidth=0.626, relheight=0.105)
        self.motor_labels = []
        self.motor_bars = []
        self.motor_bar_ratios = [0.0] * 4
        for index in range(4):
            cell = tk.Frame(panel, bg=PANEL)
            cell.place(relx=index / 4, rely=0, relwidth=0.25, relheight=0.76)
            readout = tk.Frame(cell, bg=PANEL, height=18)
            readout.pack(fill="x", padx=12, pady=(7, 0))
            readout.pack_propagate(False)
            self._label(readout, f"M{index + 1}", 10, TEXT, True).place(x=0, y=0)
            rpm = self._label(readout, "--", 10, TEXT)
            rpm.configure(width=5, anchor="e")
            rpm.place(relx=0.39, y=0, anchor="ne")
            self._label(readout, "RPM", 9, MUTED).place(relx=0.40, y=1)
            tk.Frame(readout, bg=LINE, width=1, height=13).place(relx=0.59, y=2)
            temp = self._label(readout, "-- \u00b0C", 10, MUTED, True)
            temp.configure(width=7)
            temp.place(relx=0.65, y=0)
            bar = tk.Canvas(cell, height=6, bg=PANEL, borderwidth=0, highlightthickness=0)
            bar.pack(fill="x", padx=12, pady=(5, 0))
            track = bar.create_line(3, 3, 3, 3, fill=LINE, width=6, capstyle="round")
            fill = bar.create_line(3, 3, 3, 3, fill=MOTOR_COLORS[index],
                                   width=6, capstyle="round", state="hidden")
            self.motor_labels.append((rpm, temp))
            self.motor_bars.append((bar, track, fill))
            bar.bind("<Configure>", lambda event, i=index: self._render_motor_bar(i))
        for divider in range(1, 4):
            tk.Frame(panel, bg=LINE, width=1).place(
                relx=divider / 4, rely=0.12, relheight=0.60,
            )
        tk.Frame(panel, bg=LINE, height=1).place(relx=0.015, rely=0.78, relwidth=0.97)

    def _render_motor_bar(self, index):
        bar, track, fill = self.motor_bars[index]
        width = bar.winfo_width()
        if width <= 6:
            return
        bar.coords(track, 3, 3, width - 3, 3)
        ratio = self.motor_bar_ratios[index]
        bar.itemconfigure(fill, state="normal" if ratio > 0 else "hidden")
        if ratio > 0:
            bar.coords(fill, 3, 3, 3 + (width - 6) * ratio, 3)

    def _update_motors(self, data):
        for index, (rpm_label, temp_label) in enumerate(self.motor_labels):
            rpm_valid = data is not None and data.rpm_valid
            temp_valid = data is not None and data.temperature_valid and index < data.esc_temperature_count
            rpm = data.motor_rpm[index] if rpm_valid else 0
            rpm_label.configure(text=str(rpm) if rpm_valid else "--")
            temperature = data.esc_temperature_deci_c[index] / 10 if temp_valid else 0
            temp_label.configure(
                text=f"{temperature:.0f}\u00b0C" if temp_valid else "-- \u00b0C",
                fg=RED if temp_valid and temperature >= 75 else AMBER if temp_valid else MUTED,
            )
            self.motor_bar_ratios[index] = min(1.0, max(0.0, rpm / MOTOR_BAR_MAX_RPM)) if rpm_valid else 0.0
            self._render_motor_bar(index)

    def _build_warnings(self, body):
        panel = self._panel(body)
        panel.place(relx=0.794, rely=0.895, relwidth=0.206, relheight=0.105)
        self._label(panel, "SYSTEM STATUS", 9, MUTED, True).pack(
            fill="x", padx=12, pady=(2, 0),
        )
        content = tk.Frame(panel, bg=PANEL)
        content.pack(fill="both", expand=True, padx=12, pady=(1, 4))
        self.warning_icon = self._icon(content, "warning", AMBER, size=24)
        self.warning_icon.pack(side="left", anchor="n", padx=(0, 8), pady=(3, 0))
        self.warning_scrollbar = tk.Canvas(
            content, width=7, bg=PANEL, highlightthickness=0, borderwidth=0,
        )
        self.warning_scrollbar.bind("<Configure>", lambda _event: self._draw_warning_scrollbar())
        self.warning_scrollbar.bind("<Button-1>", self._seek_warning_scrollbar)
        self.warning_scrollbar.bind("<B1-Motion>", self._seek_warning_scrollbar)
        self.warning_text = tk.Text(
            content, bg=PANEL, fg=TEXT, font=(MONO, 8), borderwidth=0,
            highlightthickness=0, width=1, height=3, wrap="word", cursor="arrow",
            yscrollcommand=self._on_warning_scroll,
        )
        self.warning_text.pack(side="left", fill="both", expand=True)
        self.warning_text.bind("<Configure>", lambda _event: self.root.after_idle(self._sync_warning_scrollbar))
        self.warning_text.tag_configure("issue", foreground=AMBER)
        self.warning_text.tag_configure("count", foreground=AMBER, font=(MONO, 8, "bold"))
        self.warning_text.tag_configure("clear", foreground=GREEN)
        self.warning_text.configure(state="disabled")

    def _resize_video(self, event):
        self.video_canvas.coords(self.video_placeholder, event.width / 2, event.height / 2)
        self.last_video_size = None

    def _serial_open(self):
        port = self.serial_link.serial_port
        return bool(
            port is not None and port.is_open
            and self.serial_link.send_thread is not None
            and self.serial_link.receive_thread is not None
            and self.serial_link.send_thread.is_alive()
            and self.serial_link.receive_thread.is_alive()
        )

    def _set_status(self, label, valid, unknown=False):
        if unknown:
            label.configure(text="--", fg=DIM)
        else:
            label.configure(text="OK" if valid else "INVALID", fg=GREEN if valid else AMBER)

    def _update_rates(self, stats):
        now = time.monotonic()
        elapsed = now - self.last_rate_check
        if elapsed >= 1.0:
            self.telemetry_hz = max(0, stats.packets_parsed - self.last_packet_count) / elapsed
            self.last_packet_count = stats.packets_parsed
            self.last_rate_check = now

    def _update_data(self):
        packet = self.get_telemetry()
        fresh = packet is not None and self.get_telemetry_age() < 1.0
        data = packet if fresh else None
        stats = self.get_parser_stats()
        self._update_rates(stats)
        usb_open = self._serial_open()
        frame, frame_time, fps = self.video_capture.get_latest_frame_info()
        video_live = frame is not None and frame_time is not None and time.monotonic() - frame_time < 1.0
        self.video_fps = fps if video_live else 0.0

        self.header_labels["usb"].configure(
            text="MAC \u2194 RIGHT USB SERIAL",
            fg=GREEN if usb_open else MUTED,
        )
        self.header_labels["air"].configure(
            text="RIGHT \u2192 AIR ESP-NOW",
            fg=GREEN if data and data.ground_link_valid else AMBER if data else MUTED,
        )
        self.header_labels["mode"].configure(
            text=(data.current_mode_name.upper() + " MODE") if data else "MODE --",
            fg=TEXT if data else MUTED,
        )
        arm_known = data is not None and data.fc_telemetry_valid and data.inav_status_valid
        armed = data.fc_armed if arm_known else False
        self.header_labels["arm"].configure(
            text="ARMED" if armed else "DISARMED" if arm_known else "ARM --",
            fg=RED if armed else TEXT if arm_known else MUTED,
        )
        self.header_labels["telemetry"].configure(
            text=f"TELEMETRY {self.telemetry_hz:.0f} Hz" if data else "TELEMETRY --",
            fg=CYAN if data else MUTED,
        )
        self.header_labels["camera"].configure(
            text=f"CAMERA {fps:.1f} FPS" if video_live else "CAMERA --",
            fg=TEXT if video_live else MUTED,
        )

        self._update_video(frame if video_live else None, frame_time, fps)
        observer = getattr(self.serial_link, "get_calibration_transmission", None)
        self.calibration_transmission = observer() if observer else CalibrationTransmission()
        self.calibration_guide.update(data, usb_open, self.get_key_mask(), self.calibration_transmission)
        command_observer = getattr(self.serial_link, "get_command_transmission", None)
        self.command_guide.update(
            data, usb_open, self.get_key_mask(),
            command_observer() if command_observer else CommandTransmission(),
            reserved=self.calibration_guide.phase in ("hold", "running"))
        active_guide = (self.command_guide if self.command_guide.phase != "idle"
                        else self.calibration_guide)
        if self.calibration_overlay is None and active_guide.phase != "idle":
            self.calibration_overlay = CalibrationOverlay(
                self.root, active_guide, background=BACKGROUND, panel=PANEL,
                text=TEXT, muted=MUTED, cyan=CYAN, amber=AMBER, line=LINE, font=MONO,
                anchor_widget=self.video_canvas)
        if self.calibration_overlay is not None:
            if self.calibration_overlay.guide is not active_guide:
                self.calibration_overlay.last_frame_key = None
                self.calibration_overlay.guide = active_guide
            self.calibration_overlay.sync()
        self._update_telemetry_labels(data, stats, usb_open)
        self._update_warnings(data, usb_open, video_live)

    def _update_video(self, frame, frame_time, fps):
        if frame is None:
            self.video_canvas.delete("frame")
            self.video_canvas.itemconfigure(self.video_placeholder, state="hidden")
            self.video_info.configure(text="FPV VIDEO  |  NO SIGNAL")
            self.last_video_time = None
            self.last_video_size = None
            return

        height, width = frame.shape[:2]
        self.video_info.configure(text=f"FPV VIDEO  |  {width} x {height}  |  {fps:.1f} FPS")
        canvas_width = max(1, self.video_canvas.winfo_width())
        canvas_height = max(1, self.video_canvas.winfo_height())
        size = (canvas_width, canvas_height)
        if frame_time == self.last_video_time and size == self.last_video_size:
            return
        scale = min(canvas_width / width, canvas_height / height)
        display_width = max(1, int(width * scale))
        display_height = max(1, int(height * scale))
        resized = cv2.resize(frame, (display_width, display_height), interpolation=cv2.INTER_AREA)
        self.video_photo = _photo_from_bgr(resized)
        if self.video_photo is None:
            return
        self.video_canvas.delete("frame")
        self.video_canvas.configure(bg=STAGE)
        self.video_canvas.create_image(
            canvas_width // 2, canvas_height // 2, image=self.video_photo, tags="frame",
        )
        self.video_canvas.itemconfigure(self.video_placeholder, state="hidden")
        self.last_video_time = frame_time
        self.last_video_size = size

    def _update_telemetry_labels(self, data, stats, usb_open):
        metrics = self.metric_labels
        metrics["battery"].configure(
            text=f"{data.battery_voltage_v:.1f} V"
            if data and data.battery_valid and data.battery_percent <= 100 else "--",
        )
        self.battery_percent_label.configure(
            text=f"{data.battery_percent}%"
            if data and data.battery_valid and data.battery_percent <= 100 else "--",
        )
        metrics["altitude"].configure(
            text=f"{data.baro_altitude_m:.1f} m" if data and data.barometer_valid else "--",
        )
        metrics["speed"].configure(
            text=f"{data.ground_speed_kph:.1f} km/h" if data and data.gps_valid else "--",
        )
        metrics["gps"].configure(
            text=f"DATA  {data.satellite_count} SAT" if data and data.gps_valid else "NO DATA" if data else "--",
            fg=GREEN if data and data.gps_valid else AMBER if data else TEXT,
        )
        metrics["home"].configure(
            text=f"{data.distance_to_home_m} m" if data and data.home_data_valid else "--",
        )
        percent = data.battery_percent if data and data.battery_valid and data.battery_percent <= 100 else 0
        self.battery_bar.coords(
            self.battery_fill, 0, 0, self.battery_bar.winfo_width() * percent / 100, 5,
        )
        self.battery_bar.itemconfigure(self.battery_fill, fill=RED if percent < 20 else GREEN)
        s = 22 / 18
        self.battery_icon.coords("charge", 6.5*s, (14.5 - 9*percent/100)*s, 11.5*s, 14.5*s)
        self.battery_icon.itemconfigure("charge", state="normal" if percent > 0 else "hidden",
                                        fill=RED if percent < 20 else GREEN)
        self.video_battery.configure(
            text=f"{data.battery_voltage_v:.1f} V   {data.battery_percent}%"
            if data and data.battery_valid and data.battery_percent <= 100 else "",
        )

        sensor_checks = {
            "MAC <> RIGHT USB": usb_open,
            "RIGHT -> AIR ESP-NOW": data.ground_link_valid if data else False,
            "PRIMARY CONTROL": data.primary_control_valid if data else False,
            "LEFT GLOVE": data.left_glove_valid if data else False,
            "LEFT IMU": data.left_imu_valid if data else False,
            "RIGHT IMU": data.right_imu_valid if data else False,
            "GPS DATA": data.gps_valid if data else False,
            "BATTERY DATA": data.battery_valid if data else False,
            "BAROMETER": data.barometer_valid if data else False,
            "ATTITUDE": data.attitude_valid if data else False,
            "FC TELEMETRY": data.fc_telemetry_valid if data else False,
        }
        for name, valid in sensor_checks.items():
            self._set_status(self.sensor_labels[name], valid, unknown=data is None and name != "MAC <> RIGHT USB")

        calibration = self.calibration_status.update(
            data, self.get_key_mask(), usb_open, transmission=self.calibration_transmission)
        self.calibration_label.configure(text=calibration, fg={
            "CALIBRATED": GREEN, "NOT CALIBRATED": AMBER,
            "CALIBRATING": CYAN, "UNAVAILABLE": DIM,
        }[calibration])

        total = stats.packets_parsed + stats.sequence_gaps
        retention = f"{stats.packets_parsed / total * 100:.2f}%" if total else "--"
        self.quality_labels["PACKET RETENTION"].configure(text=retention, fg=GREEN if total else DIM)
        self.quality_labels["SEQUENCES SKIPPED"].configure(
            text=f"{stats.sequence_gaps:,} / {total:,}" if total else "--", fg=TEXT if total else DIM,
        )
        agreement = data.rc_channel_agreement if data else None
        self.quality_labels["RC CHANNEL MATCH"].configure(
            text=f"{data.rc_accuracy_percent}% \u00b7 {agreement[0]}/{agreement[1]}" if agreement else "--",
            fg=(GREEN if data.rc_accuracy_percent >= 95 else TEXT)
            if agreement else DIM,
        )
        self.quality_labels["FC CYCLE"].configure(
            text=f"{data.cycle_time_us} us" if data and data.inav_status_valid else "--",
            fg=TEXT if data and data.inav_status_valid else DIM,
        )

        self.attitude_view.update(data)
        self.gps_view.update(data)

        self._update_motors(data)

    def _update_warnings(self, data, usb_open, video_live):
        warnings = self.issue_tracker.collect(
            data, usb_open, video_live,
            video_verified=bool(getattr(self.video_capture, "source_verified", False)),
            keyboard_listener_available=not any(
                error.startswith("Keyboard listener:") for error in self.startup_errors
            ),
        )

        current = tuple(warnings)
        if current == self.last_warnings:
            return
        self.last_warnings = current
        self.warning_text.configure(state="normal")
        self.warning_text.delete("1.0", "end")
        if warnings:
            self.warning_icon.pack(side="left", anchor="n", padx=(0, 8), pady=(3, 0), before=self.warning_text)
            self.warning_text.insert("end", f"ACTIVE ISSUES {len(warnings):02d}\n", "count")
            for message in warnings:
                self.warning_text.insert("end", f"\u2022  {message}\n", "issue")
        else:
            self.warning_icon.pack_forget()
            self.warning_text.insert("end", "NO ACTIVE ISSUES", "clear")
        self.warning_text.configure(state="disabled")
        self.root.after_idle(self._sync_warning_scrollbar)

    def _sync_warning_scrollbar(self):
        first, last = self.warning_text.yview()
        overflow = first > 0 or last < 1
        if overflow and not self.warning_scrollbar.winfo_manager():
            self.warning_scrollbar.pack(side="right", fill="y", before=self.warning_text)
        elif not overflow and self.warning_scrollbar.winfo_manager():
            self.warning_scrollbar.pack_forget()
        self._draw_warning_scrollbar()

    def _on_warning_scroll(self, _first, _last):
        self.root.after_idle(self._sync_warning_scrollbar)

    def _draw_warning_scrollbar(self):
        bar = self.warning_scrollbar
        bar.delete("all")
        height = bar.winfo_height()
        first, last = self.warning_text.yview()
        if height < 2 or (first == 0 and last == 1):
            return
        bar.create_line(3, 0, 3, height, fill=LINE, width=2)
        top = first * height
        bottom = max(top + 12, last * height)
        bar.create_rectangle(1, top, 6, min(height, bottom), fill=DIM, outline="")

    def _seek_warning_scrollbar(self, event):
        height = max(1, self.warning_scrollbar.winfo_height())
        self.warning_text.yview_moveto(max(0, min(1, event.y / height)))

    def _update(self):
        if self.closed:
            return
        self._update_data()
        self.root.after(50, self._update)

    def run(self):
        self.root.mainloop()

    def close(self):
        self.closed = True
        if self.calibration_overlay is not None:
            self.calibration_overlay.close()
        for name in ("gps_view", "attitude_view"):
            view = getattr(self, name, None)
            if view is not None:
                view.close()
        self.root.destroy()
