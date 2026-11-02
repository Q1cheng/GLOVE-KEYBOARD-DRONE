/* Map data enters exclusively through the native parsed-telemetry bridge. */
const map = L.map('map', {
  zoomControl: false, attributionControl: true, dragging: false,
  scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false,
  touchZoom: false, keyboard: false, zoomAnimation: false, fadeAnimation: false,
  markerZoomAnimation: false,
});
map.attributionControl.setPrefix(false);
const DEFAULT_ZOOM = 17;
const tiles = L.esri.basemapLayer({
  urlTemplate: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  options: {
    minZoom: 1, maxZoom: 19,
    attribution: 'Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community',
    attributionUrl: 'https://static.arcgis.com/attribution/World_Imagery',
  },
});
const records = new Map();
let initialized = false;
let tileState = 'waiting';
let tileTimeout;
let state = {position: null, heading: null, distance: null, bearing: null, history: [], segment: 0};
let marker = null;
let renderedHistory = '';
let scaleState = null;
const trail = L.polyline([], {color: '#4ed4de', weight: 2, dashArray: '5 7', lineCap: 'round', interactive: false});
const arrow = '<svg class="drone-arrow" viewBox="0 0 24 32"><path d="M12 1 23 30 12 24 1 30Z"/></svg>';
const icon = L.divIcon({className: 'drone-icon', html: `<div class="drone-halo">${arrow}<i class="position-dot" hidden></i></div>`, iconSize: [70,70], iconAnchor: [35,35]});

function availability() {
  const messages = [];
  if (!state.position) messages.push('POSITION UNAVAILABLE');
  if (state.heading === null) messages.push('HEADING UNAVAILABLE');
  if (tileState === 'failed') messages.push('MAP UNAVAILABLE');
  else if (tileState === 'loading') messages.push('LOADING SATELLITE MAP');
  document.getElementById('availability').textContent = messages.join('\n');
  document.body.classList.toggle('tiles-unavailable', tileState === 'failed');
}

function assessTiles() {
  if (!initialized) return;
  const bounds = map.getPixelBounds(), z = map.getZoom();
  const active = [...records.values()].filter(r => r.z === z &&
    (r.x + 1) * 256 > bounds.min.x && r.x * 256 < bounds.max.x &&
    (r.y + 1) * 256 > bounds.min.y && r.y * 256 < bounds.max.y);
  if (active.some(r => r.status === 'failed')) tileState = 'failed';
  else if (active.length && active.every(r => r.status === 'loaded')) tileState = 'ready';
  else tileState = 'loading';
  if (tileState !== 'loading') clearTimeout(tileTimeout);
  availability();
}
const key = c => `${c.z}/${c.x}/${c.y}`;
tiles.on('loading', () => {
  clearTimeout(tileTimeout);
  tileState = 'loading'; availability();
  tileTimeout = setTimeout(() => {tileState = 'failed'; availability();}, 12000);
});
for (const [event, status] of [['tileloadstart','loading'],['tileload','loaded'],['tileerror','failed']]) {
  tiles.on(event, e => {records.set(key(e.coords), {...e.coords, status}); assessTiles();});
}
tiles.on('tileunload', e => {records.delete(key(e.coords)); assessTiles();});
tiles.on('load', assessTiles);
setInterval(() => {if (initialized && tileState === 'failed') tiles.redraw();}, 15000);

function updateScale() {
  if (!initialized) return;
  const maxWidth = Math.min(160, map.getSize().x * .35);
  const y = map.getSize().y / 2;
  const meters = map.distance(map.containerPointToLatLng([0,y]), map.containerPointToLatLng([maxWidth,y]));
  const power = 10 ** Math.floor(Math.log10(meters));
  const length = [1,2,5,10].map(v=>v*power).filter(v=>v<=meters).pop();
  const pixels = maxWidth * length / meters;
  const format = v => v >= 1000 ? `${v / 1000} km` : `${Number(v.toFixed(2))} m`;
  document.getElementById('scale').hidden = false;
  document.getElementById('scale').style.width = `${pixels + 20}px`;
  document.getElementById('scale-mid').textContent = pixels >= 100 ? Number((length / 2 / (length >= 1000 ? 1000 : 1)).toFixed(2)) : '';
  document.getElementById('scale-end').textContent = format(length);
  scaleState = {meters: length, pixels, zoom: map.getZoom()};
}

function updateTrail() {
  // Unwrap longitude near the current viewport rather than drawing around the
  // entire world at the antimeridian. Gaps remain separate observed segments.
  const center = map.getCenter().lng;
  const groups = [];
  let segment;
  let longitude = center;
  for (const [lat, lon, id] of state.history) {
    if (id !== segment) {groups.push([]); segment = id; longitude = center;}
    longitude = lon + 360 * Math.round((longitude - lon) / 360);
    groups[groups.length-1].push([lat, longitude]);
  }
  if (state.position) {
    const p = [state.position[0], state.position[1] + 360 * Math.round((longitude-state.position[1])/360)];
    if (segment !== state.segment) groups.push([p]);
    else if (groups.length) groups[groups.length-1].push(p);
  }
  trail.setLatLngs(groups);
  trail.setStyle({opacity: state.position ? .9 : .3});
}

function update(next) {
  state = next;
  const heading = state.heading;
  const headingArrow = document.getElementById('heading-arrow');
  headingArrow.style.visibility = heading === null ? 'hidden' : 'visible';
  headingArrow.style.transform = `rotate(${heading ?? 0}deg)`;
  document.getElementById('cardinal').textContent = heading === null ? '--' : ['N','NE','E','SE','S','SW','W','NW'][Math.round(heading/45)%8];
  document.getElementById('degrees').textContent = heading === null ? '--' : `${String(Math.round(heading)%360).padStart(3,'0')}\u00b0`;
  document.getElementById('distance').textContent = state.distance === null ? '--' : `${state.distance} m`;
  document.getElementById('bearing').textContent = state.bearing === null ? '--' : `${String(Math.round(state.bearing)%360).padStart(3,'0')}\u00b0`;

  if (state.position) {
    const centerLon = initialized ? map.getCenter().lng : state.position[1];
    const position = [state.position[0], state.position[1] + 360*Math.round((centerLon-state.position[1])/360)];
    if (!initialized) {
      map.setView(position, DEFAULT_ZOOM, {animate: false});
      initialized = true;
      tiles.addTo(map);
      trail.addTo(map);
    } else if (!map.getBounds().pad(-.3).contains(position)) {
      map.panTo(position, {animate: false});
    }
    if (!marker) marker = L.marker(position, {icon, interactive: false, keyboard: false, zIndexOffset: 50}).addTo(map);
    else marker.setLatLng(position);
    const node = marker.getElement();
    node.querySelector('.drone-arrow').style.display = heading === null ? 'none' : 'block';
    node.querySelector('.drone-arrow').style.transform = `rotate(${heading ?? 0}deg)`;
    node.querySelector('.position-dot').hidden = heading !== null;
  } else if (marker) {
    marker.remove(); marker = null;
  }
  if (initialized) {
    const historyKey = JSON.stringify([state.history,state.position,state.segment,map.getCenter().lng]);
    if (historyKey !== renderedHistory) {updateTrail(); renderedHistory = historyKey;}
    updateScale();
  }
  availability();
  return true;
}
map.on('moveend zoomend', () => {updateScale(); assessTiles();});
new ResizeObserver(() => {map.invalidateSize({animate:false}); updateScale(); assessTiles();}).observe(document.body);
window.flightDeckGPS = {
  update,
  inspect: () => ({state, tileState, initialized, marker: marker ? marker.getLatLng() : null,
    trail: trail.getLatLngs(), scale: scaleState,
    headingRotation: document.getElementById('heading-arrow').style.transform,
    markerRotation: marker?.getElement().querySelector('.drone-arrow').style.transform,
    cardinal: document.getElementById('cardinal').textContent,
    degrees: document.getElementById('degrees').textContent,
    bearing: document.getElementById('bearing').textContent,
    homeMarker: false,
  }),
};
availability();
