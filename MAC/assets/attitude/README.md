# Attitude renderer

This panel uses the actual `FRAME/FULL DRONE.stl`, copied to
`models/full-drone.stl`. It does not add motors, a camera, or other parts absent
from that file. Three.js 0.180.0 and its STLLoader are bundled under `vendor/`
with the upstream MIT license. STLLoader's import is changed to a relative URL
for older macOS WebKit versions without import-map support.

The native bridge requires `pyobjc-framework-WebKit==12.2.2` in the existing
Python environment. It hosts only these assets on an ephemeral loopback port;
no internet connection, cloud service, or external browser is needed.

## Axes

The source STL uses X forward, Y left, Z up. This was verified by rigidly
registering the separately named component meshes to the assembly, not by
guessing from a screenshot. Approximate assembled component centroids in mm:

| Component | X | Y | Z |
| --- | ---: | ---: | ---: |
| TOP LEFT ARM | 278.06 | 148.86 | 298.43 |
| TOP RIGHT ARM | 278.09 | -43.56 | 298.43 |
| BOTTOM LEFT ARM | 153.98 | 137.34 | 298.43 |
| CAM HOLD LEFT | 308.30 | 65.42 | 314.37 |

The one-time right-handed transform maps CAD `(x,y,z)` to viewer `(-y,z,-x)`.
The model is centered on its bounding box and uniformly scaled by its bounding
sphere radius. At neutral, the nose points toward the fixed FWD arrow.

INAV's CRSF attitude fields are passed through unchanged by ESP32_AIR. The
existing Python telemetry properties divide signed `rad10000` values by 10,000.
The viewer uses INAV's positive pitch = nose down, positive roll = right side
down, positive yaw = clockwise convention, with order yaw, pitch, roll. See
INAV 9.1.0 `src/main/flight/imu.c` (`imuComputeQuaternionFromRPY`) and
`src/main/telemetry/crsf.c` (attitude serialization).

`scene.js` composes viewer `Ry(-yaw) * Rx(-pitch) * Rz(-roll)`.
The fixed motor labels describe neutral airframe locations, not projected
positions after yaw. The XYZ indicator uses the same body axes as the STL.

## Updates

The existing Tk main-thread 50 ms telemetry refresh sends the newest attitude
to WebKit. Numbers and model quaternion update in the same JavaScript call;
there is no interpolation or independent animation. Updates are coalesced if
WebKit is busy. As with the rest of this UI, packets arriving faster than the
refresh can be superseded by the latest snapshot.

The existing one-second packet freshness check and attitude validity bit decide
availability. Invalid/stale input immediately sends a neutral quaternion and
`--` readouts. No sensor-specific timestamp exists in the packet, so the panel
cannot detect an upstream sensor freeze while the sender still flags it valid.

## Verification

`tests/test_attitude_scene.cjs` runs browser rendering, axis, stale-state,
label-containment and canvas-pixel checks. It needs Playwright and a local server
serving this directory (`python -m http.server --bind 127.0.0.1 8769`). Set
`PLAYWRIGHT_MODULE` / `CHROME_PATH` if they are not on the default paths.
