# GPS / MAP

This is a north-up Leaflet 1.9.4 map with genuine Esri World Imagery tiles.
Esri Leaflet 3.0.15 supplies viewport-dependent data-provider attribution. Both
libraries and their licenses are bundled locally; satellite imagery needs an
internet connection and the provider's service availability/terms apply.
Tile coordinates for the viewed area are sent to Esri. No extra GPS connection
is opened and the map never decodes packet bytes.

`GPSState` receives the existing parsed `AirTelemetry` object after UI.py's
one-second freshness check. Latitude/longitude use the parser's degree
properties (E7 / 10,000,000). Position requires validity bit 1 and coordinates
inside Web Mercator's supported range. `(0,0)` is not arbitrarily rejected.
Heading exclusively uses the valid attitude yaw property (bit 7), converted
from radians to degrees and normalized. GPS course is not a heading fallback.
Bit 12 independently gates home distance and bearing.

There is no verified home coordinate source in this project, so no HOME pin is
created. The FC's home distance/bearing values are still displayed. They are
never used to synthesize home coordinates or a route.

History lasts for the UI session and retains at most 2,048 observed points.
Successive stored points must be at least one meter apart; the final displayed
endpoint is always the actual latest valid position, even if closer than one
meter to the stored anchor. Invalid/stale GPS breaks the trail into segments.
Reacquisition never draws an invented connection across an unobserved gap.
History and coordinates are not persisted to disk.

The panel initially requests no map tiles until a valid position is available.
It starts at zoom 17 and follows the aircraft when it leaves the central 40% of
the viewport. The metric scale uses Leaflet's actual geographic distance at the
current zoom and latitude, rounded to a readable 1/2/5 interval. All arrows use
the same clockwise-from-north yaw; the map itself is never rotated.

Position, heading and home readouts have independent unavailable states.
Stale position removes the live marker and dims retained historical tracks.
Missing tiles hide the incomplete imagery and show MAP UNAVAILABLE while
retaining valid telemetry overlays. Tile timeout is 12 seconds; failures retry
every 15 seconds. Provider attribution remains visible at the panel bottom.

The native GPS view reuses the approved WebKit embedding lifecycle without
editing the attitude renderer. All updates run on Tk's existing 50 ms main
thread refresh; JavaScript applies each snapshot atomically. Full bounded
history is retained in Python even if WebKit coalesces pending presentations.

Run `python -m unittest discover -s tests -p test_gps_state.py` for data tests.
Serve this folder locally on port 8770 and run `tests/test_gps_map.cjs` with
Playwright for actual imagery, heading, trail, scale and failure-state tests.
Set PLAYWRIGHT_MODULE and CHROME_PATH when those dependencies are not on the
default paths. Test positions exist only in the tests, never in the app.
