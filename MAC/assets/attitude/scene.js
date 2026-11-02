import * as THREE from './vendor/three.module.js';
import { STLLoader } from './vendor/STLLoader.js';

const stage = document.getElementById('stage');
const canvas = document.getElementById('scene');
const scene = new THREE.Scene();
scene.background = new THREE.Color('#03080b');
scene.fog = new THREE.Fog('#03080b', 5, 11);
const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 40);
camera.position.set(0, 5.5, 4.2);
camera.lookAt(0, 0, 0);
const axisCamera = new THREE.PerspectiveCamera();
axisCamera.position.set(3, 4, 5);
axisCamera.lookAt(0, 0, 0);
const aircraft = new THREE.Group();
scene.add(aircraft);
scene.add(new THREE.HemisphereLight(0xd6e1e6, 0x28323a, 1.4));
const key = new THREE.DirectionalLight(0xffffff, 3.2);
key.position.set(-3, 6, 2);
key.castShadow = true;
key.shadow.mapSize.set(1024, 1024);
Object.assign(key.shadow.camera, {left: -2, right: 2, top: 2, bottom: -2, near: .1, far: 15});
key.shadow.bias = -0.0005;
key.shadow.normalBias = 0.008;
scene.add(key);
const rim = new THREE.DirectionalLight(0x65bbcf, 0.8);
rim.position.set(3, 2, -4);
scene.add(rim);
const grid = new THREE.GridHelper(12, 32, 0x17343d, 0x10252d);
grid.position.y = -1.08;
grid.material.transparent = true;
grid.material.opacity = 0.42;
scene.add(grid);
let renderer;
let ready = false;
let state = {valid: false, pitch: 0, roll: 0, yaw: 0};
let drawCount = 0;
const errorLabel = document.getElementById('model-error');

// CAD X=forward, Y=left, Z=up, verified by registering the named arms
// and camera mount to the assembled STL. Viewer X=right, Y=up, -Z=forward.
const cadToViewer = new THREE.Matrix4().set(
  0, -1, 0, 0,
  0, 0, 1, 0,
  -1, 0, 0, 0,
  0, 0, 0, 1,
);

export function attitudeQuaternion(pitch, roll, yaw) {
  // INAV's CRSF convention: positive pitch nose-down, roll right-side-down,
  // yaw clockwise. Equivalent to CAD Rz(-yaw) * Ry(pitch) * Rx(roll).
  return new THREE.Quaternion().setFromEuler(new THREE.Euler(-pitch, -yaw, -roll, 'YXZ'));
}

function drawAxes() {
  const element = document.getElementById('axes');
  const ctx = element.getContext('2d');
  const ratio = Math.min(devicePixelRatio, 2);
  const w = element.clientWidth, h = element.clientHeight;
  element.width = w * ratio; element.height = h * ratio;
  ctx.scale(ratio, ratio);
  const origin = [w * 0.43, h * 0.69];
  const viewRotation = axisCamera.quaternion.clone().invert();
  const directions = [
    ['X', new THREE.Vector3(0, 0, -1), '#e27673'],
    ['Y', new THREE.Vector3(-1, 0, 0), '#43d5a7'],
    ['Z', new THREE.Vector3(0, 1, 0), '#4ed4de'],
  ];
  for (const [name, vector, color] of directions) {
    vector.applyQuaternion(aircraft.quaternion).applyQuaternion(viewRotation);
    const x = origin[0] + vector.x * 27, y = origin[1] - vector.y * 27;
    const angle = Math.atan2(y - origin[1], x - origin[0]);
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(...origin); ctx.lineTo(x, y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x, y);
    ctx.lineTo(x - 5 * Math.cos(angle - .4), y - 5 * Math.sin(angle - .4));
    ctx.lineTo(x - 5 * Math.cos(angle + .4), y - 5 * Math.sin(angle + .4));
    ctx.fill();
    ctx.fillStyle = '#e8f0f2'; ctx.font = '10px -apple-system';
    ctx.fillText(name, x + 5, y - 3);
  }
}

function render() {
  if (!renderer) return;
  renderer.render(scene, camera);
  drawAxes();
  drawCount++;
}

function resize() {
  if (!renderer) return;
  const w = stage.clientWidth, h = stage.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h, false);
  // Fit the bounding sphere around the fixed label rectangles. This keeps the
  // complete aircraft clear of text at every attitude without zooming on motion.
  const box = stage.getBoundingClientRect();
  let radiusPixels = Math.min(w / 2, h / 2) - 8;
  for (const label of stage.querySelectorAll('.motor,.forward')) {
    const r = label.getBoundingClientRect();
    const dx = Math.max(r.left - box.left - w / 2, w / 2 - (r.right - box.left), 0);
    const dy = Math.max(r.top - box.top - h / 2, h / 2 - (r.bottom - box.top), 0);
    radiusPixels = Math.min(radiusPixels, Math.hypot(dx, dy) - 8);
  }
  const diameterPixels = Math.max(36, radiusPixels * 2);
  const angle = Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * diameterPixels / h);
  camera.position.set(0, 5.5, 4.2).normalize().multiplyScalar(1.06 / Math.sin(angle));
  camera.aspect = w / h;
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();
  render();
}

function update(next) {
  const valid = !!next.valid && [next.pitch, next.roll, next.yaw].every(Number.isFinite);
  state = valid ? {...next, valid: true} : {valid: false, pitch: 0, roll: 0, yaw: 0};
  aircraft.quaternion.copy(attitudeQuaternion(state.pitch, state.roll, state.yaw));
  for (const name of ['pitch', 'roll', 'yaw']) {
    const degrees = state[name] * 180 / Math.PI;
    document.getElementById(name).textContent = valid
      ? (name !== 'yaw' && degrees >= 0 ? '+' : '') + degrees.toFixed(1) : '--';
  }
  render();
  return ready;
}

window.flightDeckAttitude = {
  update,
  inspect: () => ({ready, state, drawCount, vertices: aircraft.children[0]?.geometry.attributes.position.count,
    quaternion: aircraft.quaternion.toArray(),
    nose: new THREE.Vector3(0, 0, -1).applyQuaternion(aircraft.quaternion).toArray(),
    right: new THREE.Vector3(1, 0, 0).applyQuaternion(aircraft.quaternion).toArray()}),
};

try {
  renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: false});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.25;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  new ResizeObserver(resize).observe(stage);
  new STLLoader().load('./models/full-drone.stl', geometry => {
    geometry.applyMatrix4(cadToViewer);
    geometry.computeBoundingBox();
    const center = geometry.boundingBox.getCenter(new THREE.Vector3());
    geometry.translate(-center.x, -center.y, -center.z);
    geometry.computeBoundingSphere();
    geometry.scale(1 / geometry.boundingSphere.radius, 1 / geometry.boundingSphere.radius, 1 / geometry.boundingSphere.radius);
    geometry.computeVertexNormals();
    const material = new THREE.MeshStandardMaterial({
      color: 0x535b61, metalness: 0.35, roughness: 0.62, side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    aircraft.add(mesh);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 38),
      new THREE.LineBasicMaterial({color: 0x4ed4de, transparent: true, opacity: 0.18}));
    aircraft.add(edges);
    ready = true;
    update(state);
    resize();
  }, undefined, error => {
    errorLabel.textContent = 'MODEL UNAVAILABLE';
    console.error('STL load failed', error);
  });
  resize();
} catch (error) {
  errorLabel.textContent = '3D RENDERER UNAVAILABLE';
  console.error(error);
}
