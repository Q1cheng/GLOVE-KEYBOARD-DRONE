"""GPS-only WebKit view; reuses the established native embedding lifecycle."""

import json
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from attitude_view import AttitudeView, _AssetHandler
from gps_state import GPSState


class GPSView(AttitudeView):
    def __init__(self, host):
        # Keep the approved attitude view untouched. Its native positioning,
        # non-interactive WebKit surface and close lifecycle apply here too.
        self.host = host
        self.root = host.winfo_toplevel()
        self.view = None
        self.closed = False
        self.pending = None
        self.last_sent = None
        self.busy = False
        self.geometry_job = None
        self.state = GPSState()
        assets = Path(__file__).with_name('assets') / 'gps'
        self.server = ThreadingHTTPServer(
            ('127.0.0.1', 0), partial(_AssetHandler, directory=str(assets)))
        self.server.daemon_threads = True
        self.server_thread = Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.configure_binding = self.root.bind('<Configure>', self._schedule_geometry, add='+')
        self.root.after_idle(self._attach)

    def update(self, data):
        # UI.py already applies the shared one-second telemetry freshness check.
        self.pending = self.state.update(data)
        self._send()

    def _send(self):
        if (self.closed or self.view is None or self.busy
                or self.pending is None or self.pending == self.last_sent):
            return
        state = self.pending
        self.busy = True
        script = f'window.flightDeckGPS ? window.flightDeckGPS.update({json.dumps(state, allow_nan=False)}) : false'

        def completed(result, error):
            self.busy = False
            if not self.closed and error is None and result:
                self.last_sent = state

        self.view.evaluateJavaScript_completionHandler_(script, completed)
