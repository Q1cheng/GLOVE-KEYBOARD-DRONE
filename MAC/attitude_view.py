"""Local Three.js attitude scene embedded in the existing macOS Tk window."""

import json
import math
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from AppKit import NSApplication, NSMakeRect
from Foundation import NSURL, NSURLRequest
from WebKit import WKWebView, WKWebViewConfiguration


class _AssetHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


class _DisplayWebView(WKWebView):
    def acceptsFirstResponder(self):
        return False

    def hitTest_(self, _point):
        return None


class AttitudeView:
    def __init__(self, host):
        self.host = host
        self.root = host.winfo_toplevel()
        self.view = None
        self.closed = False
        self.pending = None
        self.last_sent = None
        self.busy = False
        self.geometry_job = None
        assets = Path(__file__).with_name('assets') / 'attitude'
        self.server = ThreadingHTTPServer(
            ('127.0.0.1', 0), partial(_AssetHandler, directory=str(assets)))
        self.server.daemon_threads = True
        self.server_thread = Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.configure_binding = self.root.bind('<Configure>', self._schedule_geometry, add='+')
        self.root.after_idle(self._attach)

    def _attach(self):
        if self.closed:
            return
        window = next((w for w in NSApplication.sharedApplication().windows()
                       if w.title() == self.root.title()), None)
        if window is None:
            self.root.after(50, self._attach)
            return
        self.content = window.contentView()
        self.view = _DisplayWebView.alloc().initWithFrame_configuration_(
            NSMakeRect(0, 0, 1, 1), WKWebViewConfiguration.alloc().init())
        self.view.setValue_forKey_(False, 'drawsBackground')
        self.content.addSubview_(self.view)
        port = self.server.server_address[1]
        self.view.loadRequest_(NSURLRequest.requestWithURL_(
            NSURL.URLWithString_(f'http://127.0.0.1:{port}/index.html')))
        self._position()

    def _schedule_geometry(self, _event=None):
        if not self.closed and self.geometry_job is None:
            self.geometry_job = self.root.after_idle(self._position)

    def _position(self):
        self.geometry_job = None
        if self.closed or self.view is None:
            return
        x = self.host.winfo_rootx() - self.root.winfo_rootx()
        y = self.host.winfo_rooty() - self.root.winfo_rooty()
        width, height = self.host.winfo_width(), self.host.winfo_height()
        bottom = self.content.bounds().size.height - y - height
        self.view.setFrame_(NSMakeRect(x, bottom, width, height))

    def update(self, data):
        # Called only by Tk's main-thread telemetry refresh. The parser already
        # converts CRSF rad10000 values to radians; never convert them twice.
        valid = bool(data and data.attitude_valid)
        angles = (data.pitch_radians, data.roll_radians, data.yaw_radians) if valid else (0, 0, 0)
        valid = valid and all(math.isfinite(value) for value in angles)
        self.pending = (valid, *(angles if valid else (0, 0, 0)))
        self._send()

    def _send(self):
        if self.closed or self.view is None or self.busy or self.pending == self.last_sent:
            return
        state = self.pending
        if state is None:
            return
        self.busy = True
        payload = dict(zip(('valid', 'pitch', 'roll', 'yaw'), state))
        script = f'window.flightDeckAttitude ? window.flightDeckAttitude.update({json.dumps(payload)}) : false'

        def completed(result, error):
            self.busy = False
            if self.closed:
                return
            if error is None and result:
                self.last_sent = state
            # If loading has not finished, the next existing UI refresh retries.

        self.view.evaluateJavaScript_completionHandler_(script, completed)

    def close(self):
        self.closed = True
        if self.geometry_job is not None:
            self.root.after_cancel(self.geometry_job)
        self.root.unbind('<Configure>', self.configure_binding)
        if self.view is not None:
            self.view.stopLoading()
            self.view.removeFromSuperview()
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=1)
