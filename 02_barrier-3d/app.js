/*
 * 방음벽 폐쇄감 검토 모델 (three.js)
 * 모든 치수는 config.js(window.BARRIER_CONFIG)에서 읽어 배치를 계산합니다.
 * 좌표계: X = 동, Y = 북, Z = 위 (m). three.js 내부 변환: (x, y, z) → (x, z, -y)
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const CFG = window.BARRIER_CONFIG;
if (!CFG) {
  const e = document.getElementById('err');
  e.style.display = 'block';
  e.textContent = '설정(config.js)을 불러오지 못했습니다. config.js가 index.html과 같은 폴더에 있는지 확인하십시오.';
  throw new Error('BARRIER_CONFIG missing');
}

const W = (x, y, z) => new THREE.Vector3(x, z, -y);
const DEG = Math.PI / 180;
const fmt = (v, d = 1) => (Math.round(v * 10 ** d) / 10 ** d).toString();

/* ================================================================
 * 1. 배치 계산 (설정 → 좌표)
 * ================================================================ */
const L = (() => {
  const r = CFG.roads, s = CFG.site, w = CFG.wall, v = CFG.villa;
  const Wm = r.north.width, We = r.east.width, Wl = r.local.width, sw = r.sidewalk;
  const Yn = s.depth;                                   // 북측 필지 경계(벽 선)
  const Ln = w.northArmLength;                          // 북측 팔 끝 X = 동측 도로 서쪽 가장자리
  const Xv = Math.min(s.villaZoneWidth, Ln - Wl - 10);  // 빌라 구간 폭
  const wallLine = Yn - 0.2;                            // 벽 중심선(필지 경계에서 0.2 m 안쪽)
  const wallLineX = Ln - 0.2;
  const Le = Math.max(0, Math.min(w.eastArmLength, Yn - Wl - 2));
  const midY0 = Wl + (Yn - Wl - Wl) / 2, midY1 = midY0 + Wl; // 중간 소로
  const Rw = CFG.research.blockWidth;
  const eastEdge = Ln + We + Rw;                        // 구역 동단
  const northEdge = Yn + Wm;                            // 구역 북단(북측 도로 북쪽 가장자리)
  const cx = eastEdge / 2, cy = Yn / 2;                 // 장면 중심
  return { Wm, We, Wl, sw, Yn, Ln, Xv, wallLine, wallLineX, Le, eastFrom: wallLine, eastTo: wallLine - Le,
    midY0, midY1, Rw, eastEdge, northEdge, cx, cy, setback: s.setback };
})();

/* 빌라 치수 */
const VL = (() => {
  const v = CFG.villa;
  const fh = v.floorHeight, n = v.floors;
  const eave = n * fh + v.parapet;
  return { fh, n, eave, w: v.footprintW, d: v.footprintD, gap: v.gap, piloti: v.piloti, parapet: v.parapet };
})();

/* 빌라 열 배치: 각 필지에 남·북 두 줄(깊이가 모자라면 한 줄) */
const villaRows = [];
{
  const parcels = [[L.midY1, L.Yn], [L.Wl, L.midY0]];
  for (const [y0, y1] of parcels) {
    const depth = y1 - y0;
    villaRows.push(y1 - L.setback - VL.d);                      // 북쪽 줄(외벽 = 경계 - 이격)
    if (depth >= 2 * VL.d + 2 * L.setback + 4) villaRows.push(y0 + L.setback);
  }
}
const villaCols = [];
for (let x0 = 2; x0 + VL.w <= L.Xv - 1; x0 += VL.w + VL.gap) villaCols.push(x0);

/* 창 시점·단면 위치: 북쪽 줄 가운데 동 */
const facadeY = L.Yn - L.setback;                              // 벽 쪽 외벽 면
const winCol = villaCols[Math.floor((villaCols.length - 1) / 2)] ?? 2;
const WIN_X = winCol + VL.w / 2;
const CUT_X = winCol + VL.w + VL.gap / 2;
const eyeZ = f => (f - 1) * VL.fh + CFG.floorAnalysis.eyeHeight;

/* ================================================================
 * 2. 렌더러 · 카메라 · 조명
 * ================================================================ */
const stageEl = document.getElementById('stage');
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.setClearColor(0xdfe7ee);
stageEl.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0xdfe7ee, 700, 2600);
const cam = new THREE.PerspectiveCamera(50, 1, 0.1, 4000);
const orthoCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 4000);
let activeCam = cam;
const controls = new OrbitControls(cam, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = 0.08; controls.maxPolarAngle = Math.PI * 0.52;
const controlsO = new OrbitControls(orthoCam, renderer.domElement);
controlsO.enableDamping = true; controlsO.enableRotate = false; controlsO.enabled = false;

scene.add(new THREE.HemisphereLight(0xe8eff6, 0xb8b4a4, 0.85));
const sun = new THREE.DirectionalLight(0xfff2dd, 2.2);
sun.castShadow = true;
sun.shadow.mapSize.set(4096, 4096);
const shR = Math.max(300, L.eastEdge * 0.9);
sun.shadow.camera.left = -shR; sun.shadow.camera.right = shR;
sun.shadow.camera.top = shR; sun.shadow.camera.bottom = -shR;
sun.shadow.camera.near = 100; sun.shadow.camera.far = 1600;
sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.4;
const sunTarget = new THREE.Object3D(); sunTarget.position.copy(W(L.cx, L.cy, 0));
scene.add(sunTarget); sun.target = sunTarget; scene.add(sun);

{ // 간이 환경맵(유리 반사용)
  const face = (top, horizon, bottom) => { const c = document.createElement('canvas'); c.width = c.height = 64;
    const g = c.getContext('2d'); const gr = g.createLinearGradient(0, 0, 0, 64);
    gr.addColorStop(0, top); gr.addColorStop(0.55, horizon); gr.addColorStop(1, bottom);
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64); return c; };
  const flat = col => { const c = document.createElement('canvas'); c.width = c.height = 64;
    const g = c.getContext('2d'); g.fillStyle = col; g.fillRect(0, 0, 64, 64); return c; };
  const side = () => face('#c3d6e6', '#eef2f2', '#9aa08c');
  const ct = new THREE.CubeTexture([side(), side(), flat('#d3e2ee'), flat('#9aa08c'), side(), side()]);
  ct.colorSpace = THREE.SRGBColorSpace; ct.needsUpdate = true;
  scene.environment = ct;
}

/* 태양 위치: 위도·적위·시간각으로 계산 (방위각은 남쪽 기준 서쪽 +) */
function solar(latDeg, declDeg, hourAngleDeg) {
  const f = latDeg * DEG, d = declDeg * DEG, h = hourAngleDeg * DEG;
  const el = Math.asin(Math.sin(f) * Math.sin(d) + Math.cos(f) * Math.cos(d) * Math.cos(h));
  const az = Math.atan2(Math.sin(h), Math.cos(h) * Math.sin(f) - Math.tan(d) * Math.cos(f));
  return { el: el / DEG, az: az / DEG };
}
const LAT = CFG.latitudeDeg;
const SUNS = {
  winter:  { ...solar(LAT, -23.44, 0), label: '동지 정오' },
  equinox: { ...solar(LAT, 0, 0), label: '춘분 정오' },
  summer:  { ...solar(LAT, 23.44, 0), label: '하지 정오' },
  pm3:     { ...solar(LAT, 0, 45), label: '춘분 오후 3시' }
};
function setSun(key) {
  const s = SUNS[key]; state.sun = key;
  const R = 700, el = s.el * DEG, az = s.az * DEG;
  sun.position.copy(W(L.cx - Math.sin(az) * Math.cos(el) * R, L.cy - Math.cos(az) * Math.cos(el) * R, Math.sin(el) * R));
}

/* ================================================================
 * 3. 텍스처 · 재질
 * ================================================================ */
function tex(w, h, draw, repX = 1, repY = 1) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(repX, repY);
  t.anisotropy = 8; t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
const texT1 = () => tex(8, 256, g => { g.clearRect(0, 0, 8, 256); g.fillStyle = '#fff'; g.fillRect(0, 0, 8, 15); }); // 5 cm 주기, 선 3 mm
const texT2 = () => tex(256, 128, g => { g.clearRect(0, 0, 256, 128); g.fillStyle = '#fff'; g.beginPath(); g.arc(64, 32, 7.7, 0, 7); g.arc(192, 96, 7.7, 0, 7); g.fill(); });
const texT4 = () => tex(128, 128, g => { g.fillStyle = '#aeb4b1'; g.fillRect(0, 0, 128, 128); g.fillStyle = '#848a87';
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) { g.beginPath(); g.arc(16 + i * 32, 16 + j * 32, 5, 0, 7); g.fill(); } });
const texT6 = () => tex(256, 128, g => { g.fillStyle = '#b6b3ac'; g.fillRect(0, 0, 256, 128); g.strokeStyle = '#948f86'; g.lineWidth = 3;
  g.strokeRect(1, 1, 254, 126); g.fillStyle = 'rgba(0,0,0,0.05)'; for (let i = 0; i < 30; i++) g.fillRect(Math.random() * 256, Math.random() * 128, 20, 6); });
function texVine(dense) { return tex(512, 512, g => { g.clearRect(0, 0, 512, 512);
  const n = dense ? 900 : 260;
  for (let i = 0; i < n; i++) { const y = dense ? Math.random() * 512 : 512 - Math.random() * Math.random() * 512;
    g.fillStyle = `rgba(255,255,255,${0.5 + Math.random() * 0.5})`; g.beginPath(); g.arc(Math.random() * 512, y, 4 + Math.random() * 9, 0, 7); g.fill(); } }); }
const brickTex = tex(64, 64, g => { g.fillStyle = '#9a6a55'; g.fillRect(0, 0, 64, 64); g.fillStyle = 'rgba(255,255,255,0.09)';
  for (let j = 0; j < 8; j++) g.fillRect(0, j * 8, 64, 1); }, 6, 12);
function facadeTex(floors) { return tex(300, 240, g => { // 한 층 ×3칸
  g.fillStyle = '#9a6a55'; g.fillRect(0, 0, 300, 240);
  g.fillStyle = 'rgba(255,255,255,0.08)'; for (let j = 0; j < 16; j++) g.fillRect(0, j * 15, 300, 2);
  g.fillStyle = '#b3b3ae'; g.fillRect(0, 218, 300, 22);
  for (let i = 0; i < 3; i++) { const x = 22 + i * 100;
    g.fillStyle = '#2e3c47'; g.fillRect(x, 55, 56, 120);
    g.fillStyle = 'rgba(255,255,255,0.25)'; g.fillRect(x + 4, 60, 20, 110);
    g.fillStyle = '#8e9598'; g.fillRect(x - 4, 175, 64, 8); }
}, 3, floors); }
function officeTex(spandrel, glass, cols) { return tex(256, 160, g => {
  g.fillStyle = spandrel; g.fillRect(0, 0, 256, 160);
  const cw = 256 / cols;
  for (let i = 0; i < cols; i++) { g.fillStyle = glass; g.fillRect(i * cw + 5, 48, cw - 10, 104);
    g.fillStyle = 'rgba(255,255,255,0.28)'; g.fillRect(i * cw + 8, 52, (cw - 16) * 0.4, 96); } }); }

const mat = {
  farm: new THREE.MeshStandardMaterial({ color: 0xaeb890, roughness: 1 }),
  plate: new THREE.MeshStandardMaterial({ color: 0xd8d8d2, roughness: 0.95 }),
  road: new THREE.MeshStandardMaterial({ color: 0x87898c, roughness: 0.95 }),
  walk: new THREE.MeshStandardMaterial({ color: 0xc8c8c3, roughness: 0.95 }),
  white: new THREE.MeshStandardMaterial({ color: 0xf2f2ee, roughness: 0.8 }),
  yellow: new THREE.MeshStandardMaterial({ color: 0xd8b23c, roughness: 0.8 }),
  green: new THREE.MeshStandardMaterial({ color: 0x7d9a6f, roughness: 1 }),
  trunk: new THREE.MeshStandardMaterial({ color: 0x6d5a44, roughness: 1 }),
  crown: new THREE.MeshStandardMaterial({ color: 0x5d7f52, roughness: 1 }),
  brick: new THREE.MeshStandardMaterial({ map: brickTex, roughness: 0.9 }),
  slab: new THREE.MeshStandardMaterial({ color: 0xb9b7b2, roughness: 0.9 }),
  tank: new THREE.MeshStandardMaterial({ color: 0xd9d6ce, roughness: 0.6 }),
  ghouse: new THREE.MeshStandardMaterial({ color: 0xe9ecec, roughness: 0.4, metalness: 0.05 }),
  houseWall: new THREE.MeshStandardMaterial({ color: 0xd6d0c2, roughness: 0.95 }),
  houseRoof: new THREE.MeshStandardMaterial({ color: 0x5a6a74, roughness: 0.85 }),
  carBody: new THREE.MeshStandardMaterial({ color: 0x9aa2a8, roughness: 0.4, metalness: 0.3 }),
  person: new THREE.MeshStandardMaterial({ color: 0x35404a, roughness: 0.8 }),
  concrete: new THREE.MeshStandardMaterial({ color: 0xc2bfb7, roughness: 0.95, side: THREE.DoubleSide }),
  steel: new THREE.MeshStandardMaterial({ color: 0x5c6663, roughness: 0.5, metalness: 0.35 }),
  wood: new THREE.MeshStandardMaterial({ color: 0x8a6b4a, roughness: 0.8 }),
  cap: new THREE.MeshStandardMaterial({ color: 0x3f4644, roughness: 0.45, metalness: 0.35 }),
  wire: new THREE.MeshStandardMaterial({ color: 0xd2d7d6, roughness: 0.35, metalness: 0.4 }),
  t5: new THREE.MeshStandardMaterial({ color: 0x4c6b52, roughness: 0.7 }),
  parking: new THREE.MeshStandardMaterial({ color: 0x9fa0a2, roughness: 0.95 })
};

const UNIT = new THREE.BoxGeometry(1, 1, 1);
const IDENT = new THREE.Quaternion();
function m4(x, y, z, sx, sy, sz, q) { return new THREE.Matrix4().compose(W(x, y, z), q || IDENT, new THREE.Vector3(sx, sz, sy)); }
function inst(list, material, opts = {}) {
  const im = new THREE.InstancedMesh(UNIT, material, Math.max(1, list.length));
  list.forEach((m, i) => im.setMatrixAt(i, m));
  im.count = list.length;
  im.instanceMatrix.needsUpdate = true;
  im.castShadow = opts.cast !== false; im.receiveShadow = true;
  return im;
}
function bx(w, d, h, material, x, y, z, opts = {}) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  m.position.copy(W(x, y, z));
  m.castShadow = opts.cast !== false; m.receiveShadow = true;
  if (opts.q) m.quaternion.copy(opts.q);
  return m;
}
function rect(x0, x1, y0, y1, z, th, material, opts = {}) {
  return bx(x1 - x0, y1 - y0, th, material, (x0 + x1) / 2, (y0 + y1) / 2, z, { cast: false, ...opts });
}

/* ================================================================
 * 4. 지형 · 도로
 * ================================================================ */
const site = new THREE.Group(); scene.add(site);
const ROAD_W = -80, ROAD_E = L.eastEdge + 60, ROAD_S = -80, ROAD_N = L.northEdge + 80;
{
  const base = new THREE.Mesh(new THREE.PlaneGeometry(4000, 4000), mat.farm);
  base.rotation.x = -Math.PI / 2; base.position.copy(W(L.cx, L.cy, -0.02)); base.receiveShadow = true;
  site.add(base);
  // 논 패치 (구역 밖)
  const paddies = [], paddyColors = [];
  const inDistrict = (x, y) => (x > -15 && x < L.eastEdge + 15 && y > -15 && y < L.northEdge + 5) ||
    (x > L.Ln - 5 && x < L.Ln + L.We + 5) || (y > L.Yn - 5 && y < L.northEdge + 5 && x > ROAD_W - 40);
  for (let gx = -560; gx < L.eastEdge + 500; gx += 42) for (let gy = -560; gy < L.northEdge + 600; gy += 26) {
    if (inDistrict(gx, gy) || inDistrict(gx + 36, gy + 21)) continue;
    if (Math.random() < 0.25) continue;
    paddies.push(m4(gx + 18, gy + 10.5, 0.0, 36, 21, 0.06));
    paddyColors.push(new THREE.Color().setHSL(0.22 + Math.random() * 0.06, 0.28 + Math.random() * 0.18, 0.5 + Math.random() * 0.14));
  }
  const pim = inst(paddies, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 1 }), { cast: false });
  paddyColors.forEach((c, i) => pim.setColorAt(i, c)); if (pim.instanceColor) pim.instanceColor.needsUpdate = true;
  site.add(pim);

  const { Wm, We, Wl, sw, Yn, Ln, Xv, midY0, midY1 } = L;
  // 구역 플레이트
  site.add(rect(0, Ln, 0, Yn, 0.02, 0.05, mat.plate));
  site.add(rect(Ln + We, L.eastEdge, 0, Yn, 0.02, 0.05, mat.plate));
  // 도로면
  site.add(rect(ROAD_W, ROAD_E, Yn, Yn + Wm, 0.05, 0.05, mat.road));   // 북측 도로
  site.add(rect(Ln, Ln + We, ROAD_S, ROAD_N, 0.05, 0.05, mat.road));   // 동측 도로
  site.add(rect(0, Ln, 0, Wl, 0.05, 0.05, mat.road));                  // 남측 소로
  site.add(rect(0, Xv, midY0, midY1, 0.05, 0.05, mat.road));           // 중간 소로
  site.add(rect(Xv, Xv + Wl, Wl, Yn, 0.05, 0.05, mat.road));           // 동측 소로
  // 보도
  const swl = Math.min(sw, Wl / 4);
  site.add(rect(ROAD_W, ROAD_E, Yn, Yn + sw, 0.14, 0.14, mat.walk));
  site.add(rect(ROAD_W, ROAD_E, Yn + Wm - sw, Yn + Wm, 0.14, 0.14, mat.walk));
  site.add(rect(Ln, Ln + sw, ROAD_S, ROAD_N, 0.14, 0.14, mat.walk));
  site.add(rect(Ln + We - sw, Ln + We, ROAD_S, ROAD_N, 0.14, 0.14, mat.walk));
  for (const [y0, y1] of [[0, swl], [Wl - swl, Wl]]) site.add(rect(0, Ln, y0, y1, 0.14, 0.14, mat.walk));
  for (const [y0, y1] of [[midY0, midY0 + swl], [midY1 - swl, midY1]]) site.add(rect(0, Xv, y0, y1, 0.14, 0.14, mat.walk));
  for (const [x0, x1] of [[Xv, Xv + swl], [Xv + Wl - swl, Xv + Wl]]) site.add(rect(x0, x1, Wl, Yn, 0.14, 0.14, mat.walk));
  // 차선: 차로 폭을 차로 수로 나눠 경계선 표시
  const dashes = [], centers = [];
  const laneLines = (edge0, width, lanes, horiz, from, to) => {
    const carriage = width - 2 * sw, lw = carriage / lanes, c0 = edge0 + sw;
    for (let k = 1; k < lanes; k++) {
      const pos = c0 + lw * k;
      const isCenter = lanes % 2 === 0 && k === lanes / 2;
      if (isCenter) {
        if (horiz) centers.push(m4((from + to) / 2, pos - 0.18, 0.09, to - from, 0.13, 0.02), m4((from + to) / 2, pos + 0.18, 0.09, to - from, 0.13, 0.02));
        else centers.push(m4(pos - 0.18, (from + to) / 2, 0.09, 0.13, to - from, 0.02), m4(pos + 0.18, (from + to) / 2, 0.09, 0.13, to - from, 0.02));
      } else {
        for (let a = from + 2; a < to - 2; a += 8) dashes.push(horiz ? m4(a + 2, pos, 0.09, 4, 0.15, 0.02) : m4(pos, a + 2, 0.09, 0.15, 4, 0.02));
      }
    }
  };
  laneLines(Yn, Wm, CFG.roads.north.lanes, true, ROAD_W, ROAD_E);
  laneLines(Ln, We, CFG.roads.east.lanes, false, ROAD_S, ROAD_N);
  for (let x = 2; x < Ln - 4; x += 8) dashes.push(m4(x + 2, Wl / 2, 0.09, 4, 0.15, 0.02));
  for (let x = 2; x < Xv - 4; x += 8) dashes.push(m4(x + 2, (midY0 + midY1) / 2, 0.09, 4, 0.15, 0.02));
  for (let y = Wl + 2; y < Yn - 4; y += 8) dashes.push(m4(Xv + Wl / 2, y + 2, 0.09, 0.15, 4, 0.02));
  site.add(inst(dashes, mat.white, { cast: false }));
  site.add(inst(centers, mat.yellow, { cast: false }));
}

/* ================================================================
 * 5. 수목 · 농촌 맥락 (치수 비기준)
 * ================================================================ */
{
  const trunks = [], crowns = [], crownCol = [];
  const addTree = (x, y, s = 1) => {
    trunks.push(m4(x, y, 1.5 * s, 0.3, 0.3, 3 * s));
    crowns.push(m4(x, y, 4.8 * s, 4.4 * s, 4.4 * s, 4.2 * s));
    crownCol.push(new THREE.Color().setHSL(0.29 + Math.random() * 0.05, 0.3, 0.32 + Math.random() * 0.1));
  };
  for (let x = ROAD_W + 10; x < ROAD_E; x += 14) addTree(x, L.northEdge - L.sw - 0.7);          // 북측 도로 북쪽 가로수
  for (let y = ROAD_S + 10; y < ROAD_N; y += 14) { addTree(L.Ln + L.sw + 0.7, y); addTree(L.Ln + L.We - L.sw - 0.7, y); }
  const tim = inst(trunks, mat.trunk);
  const cim = new THREE.InstancedMesh(new THREE.SphereGeometry(0.5, 7, 6), mat.crown, crowns.length);
  crowns.forEach((m, i) => { cim.setMatrixAt(i, m); cim.setColorAt(i, crownCol[i]); });
  cim.instanceMatrix.needsUpdate = true; cim.castShadow = true; cim.receiveShadow = true;
  site.add(tim, cim);
  // 농가 마을(북측 도로 너머 북서 · 구역 서쪽)
  const walls = [], roofs = [];
  const qRoof = new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0));
  const addHouse = (x, y, rot) => {
    const w = 7 + Math.random() * 3, d = 5.5 + Math.random() * 2, h = 2.8;
    const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, rot, 0));
    walls.push(new THREE.Matrix4().compose(W(x, y, h / 2), q, new THREE.Vector3(w, h, d)));
    roofs.push(new THREE.Matrix4().compose(W(x, y, h + 0.55), q.clone().multiply(qRoof), new THREE.Vector3(w * 1.15, 2.1, d * 1.15)));
  };
  for (let i = 0; i < 14; i++) addHouse(-115 + Math.random() * 72, L.northEdge + 25 + Math.random() * 60, Math.random() * 0.6 - 0.3);
  for (let i = 0; i < 14; i++) addHouse(-172 + Math.random() * 105, 20 + Math.random() * 60, Math.random() * 0.6 - 0.3);
  site.add(inst(walls, mat.houseWall));
  const rim = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.5, 0.5, 1, 3, 1), mat.houseRoof, roofs.length);
  roofs.forEach((m, i) => rim.setMatrixAt(i, m)); rim.instanceMatrix.needsUpdate = true; rim.castShadow = true; site.add(rim);
  // 비닐하우스
  const qgh = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI / 2, 0, 0));
  const ghs = [];
  const N = L.northEdge;
  const ghSpots = [[-60, N + 30], [-30, N + 45], [-95, N + 70], [60, N + 20], [110, N + 28], [170, N + 18], [-40, -30], [30, -40], [-70, 60], [L.eastEdge + 40, 60], [L.eastEdge + 60, N + 10], [150, N + 40]];
  for (const [x, y] of ghSpots) for (let k = 0; k < 2; k++) ghs.push(new THREE.Matrix4().compose(W(x + k * 8, y, 0), qgh, new THREE.Vector3(1, 1, 1)));
  const ghm = new THREE.InstancedMesh(new THREE.CylinderGeometry(3, 3, 22, 12), mat.ghouse, ghs.length);
  ghs.forEach((m, i) => ghm.setMatrixAt(i, m)); ghm.instanceMatrix.needsUpdate = true; ghm.castShadow = true; site.add(ghm);
}

/* ================================================================
 * 6. 건물
 * ================================================================ */
const villaGroup = new THREE.Group(); scene.add(villaGroup);
{
  const resFloors = VL.piloti ? VL.n - 1 : VL.n;
  const bodyZ0 = VL.piloti ? VL.fh : 0;
  const bodyH = resFloors * VL.fh;
  const facadeMat = new THREE.MeshStandardMaterial({ map: facadeTex(Math.max(1, resFloors)), roughness: 0.85 });
  const bodyMats = [mat.brick, mat.brick, mat.slab, mat.brick, facadeMat, facadeMat];
  const bodyGeo = new THREE.BoxGeometry(VL.w, bodyH, VL.d);
  const cols = [], tanks = [], balc = [], rails = [], cars = [];
  for (const ry of villaRows) for (const x0 of villaCols) {
    const cx = x0 + VL.w / 2, cy = ry + VL.d / 2;
    if (VL.piloti) {
      for (const ox of [0.75, VL.w / 2, VL.w - 0.75]) for (const oy of [0.75, VL.d / 2, VL.d - 0.75])
        cols.push(m4(x0 + ox, ry + oy, VL.fh / 2, 0.55, 0.55, VL.fh));
      villaGroup.add(bx(VL.w, VL.d, 0.35, mat.slab, cx, cy, VL.fh - 0.18));
      if (Math.random() < 0.5) cars.push(m4(x0 + 3.4, ry + 3.5, 0.75, 1.8, 4.4, 1.3));
      if (Math.random() < 0.5) cars.push(m4(x0 + VL.w - 3.4, ry + VL.d - 4, 0.75, 1.8, 4.4, 1.3));
    }
    if (bodyH > 0) {
      const body = new THREE.Mesh(bodyGeo, bodyMats);
      body.position.copy(W(cx, cy, bodyZ0 + bodyH / 2)); body.castShadow = body.receiveShadow = true;
      villaGroup.add(body);
    }
    villaGroup.add(bx(VL.w, VL.d, VL.parapet, mat.brick, cx, cy, VL.n * VL.fh + VL.parapet / 2));
    tanks.push(m4(x0 + 3, ry + 4, VL.n * VL.fh + VL.parapet + 0.7, 1.8, 1.8, 1.4));
    for (let f = 0; f < resFloors; f++) { const z = bodyZ0 + f * VL.fh;
      balc.push(m4(x0 + VL.w * 0.72, ry - 0.6, z + 0.08, 2.8, 1.2, 0.16));
      rails.push(m4(x0 + VL.w * 0.72, ry - 1.15, z + 0.6, 2.8, 0.08, 1.05)); }
  }
  villaGroup.add(inst(cols, mat.concrete), inst(tanks, mat.tank), inst(balc, mat.slab),
    inst(rails, new THREE.MeshStandardMaterial({ color: 0x4a5258, roughness: 0.5 })), inst(cars, mat.carBody));
}
const officeTopEye = { x: 0, y: 0, z: 0, ok: false };
{
  const mk = (x0, x1, y0, y1, floors, fh, spandrel, glass) => {
    if (x1 - x0 < 8 || y1 - y0 < 8) return;
    const t = officeTex(spandrel, glass, 5); t.repeat.set(Math.max(2, Math.round((x1 - x0) / 8)), floors);
    const t2 = t.clone(); t2.repeat.set(Math.max(2, Math.round((y1 - y0) / 8)), floors); t2.needsUpdate = true;
    const fm = new THREE.MeshStandardMaterial({ map: t, roughness: 0.7 });
    const fm2 = new THREE.MeshStandardMaterial({ map: t2, roughness: 0.7 });
    const h = floors * fh;
    const m = new THREE.Mesh(new THREE.BoxGeometry(x1 - x0, h, y1 - y0), [fm2, fm2, mat.slab, mat.slab, fm, fm]);
    m.position.copy(W((x0 + x1) / 2, (y0 + y1) / 2, h / 2)); m.castShadow = m.receiveShadow = true;
    scene.add(m);
    scene.add(bx(x1 - x0, y1 - y0, 0.8, mat.slab, (x0 + x1) / 2, (y0 + y1) / 2, h + 0.4));
  };
  const o = CFG.office, r = CFG.research;
  // 업무 용지: 빌라 구간 동쪽 소로 ~ 동측 도로 사이, 남·북 두 동 + 가운데 주차장
  const ox0 = L.Xv + L.Wl + 5, ox1 = L.Ln - 5;
  const oy1 = L.Yn - L.setback, oy0 = L.Wl + 5;
  const bd = Math.min(26, (oy1 - oy0) / 3);
  mk(ox0, ox1, oy1 - bd, oy1, o.floors, o.floorHeight, '#585f66', '#aebfc9');
  mk(ox0, ox1, oy0, oy0 + bd, o.floors, o.floorHeight, '#6a6459', '#c2bcae');
  if (ox1 - ox0 > 8) {
    site.add(rect(ox0, ox1, oy0 + bd + 4, oy1 - bd - 4, 0.06, 0.05, mat.parking));
    officeTopEye.x = ox1 - 0.8; officeTopEye.y = (L.eastTo + L.eastFrom) / 2; officeTopEye.z = (o.floors - 1) * o.floorHeight + CFG.floorAnalysis.eyeHeight;
    officeTopEye.y = Math.min(oy1 - 1, Math.max(oy1 - bd + 1, officeTopEye.y));
    officeTopEye.ok = true;
  }
  // 동측 도로 건너편 연구 용지
  mk(L.Ln + L.We + 6, L.eastEdge - 5, L.Wl + 5, L.Yn - 8, r.floors, r.floorHeight, '#5e6a72', '#b4c4cb');
}
/* 척도 기준물: 사람 1.5 m · 화물차 약 4 m */
const person = new THREE.Group();
{
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.21, 1.05, 10), mat.person); body.position.y = 0.72;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.135, 12, 10), new THREE.MeshStandardMaterial({ color: 0xc9a689, roughness: 0.8 })); head.position.y = 1.36;
  body.castShadow = head.castShadow = true;
  person.add(body, head); person.position.copy(W(villaCols[0] + VL.w + VL.gap / 2, L.Yn - 12, 0)); scene.add(person);
  const truck = new THREE.Group();
  truck.add(bx(10, 2.5, 3, new THREE.MeshStandardMaterial({ color: 0xdcdcd6, roughness: 0.5 }), -1.2, 0, 2.5));
  truck.add(bx(2.6, 2.4, 2.7, new THREE.MeshStandardMaterial({ color: 0x33526b, roughness: 0.4 }), 5.3, 0, 2.15));
  const wq = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, Math.PI / 2));
  const wgeo = new THREE.CylinderGeometry(0.52, 0.52, 0.4, 14);
  for (const wx of [-4.5, -2.2, 4.9]) for (const wy of [-1.1, 1.1]) {
    const w = new THREE.Mesh(wgeo, mat.cap); w.quaternion.copy(wq); w.position.copy(W(wx, wy, 0.52)); w.castShadow = true; truck.add(w); }
  truck.position.copy(W(L.Ln * 0.6, L.Yn + L.Wm * 0.62, 0)); scene.add(truck);
}

/* ================================================================
 * 7. 방음벽
 * ================================================================ */
const TYPE_INFO = {
  T1: { label: 'T1 투명 + 수평선', trans: '60~70%', clear: true },
  T2: { label: 'T2 투명 + 점무늬', trans: '75%', clear: true },
  T3: { label: 'T3 투명 + 와이어', trans: '80%', clear: true },
  T4: { label: 'T4 알루미늄 흡음', trans: '0%', clear: false },
  T5: { label: 'T5 칼라강판 흡음', trans: '0%', clear: false },
  T6: { label: 'T6 콘크리트 반사', trans: '0%', clear: false },
  T10: { label: 'T10 벽면 녹화(T4)', trans: '0%', clear: false }
};
const PRESETS = {
  T1: { lower: 'T4', lowerH: 0, upper: 'T1', bend: false },
  T2: { lower: 'T4', lowerH: 0, upper: 'T2', bend: false },
  T3: { lower: 'T4', lowerH: 0, upper: 'T3', bend: false },
  T4: { lower: 'T4', lowerH: 0, upper: 'T4', bend: false },
  T5: { lower: 'T4', lowerH: 0, upper: 'T5', bend: false },
  T6: { lower: 'T4', lowerH: 0, upper: 'T6', bend: false },
  T7: { lower: 'T4', lowerH: 2, upper: 'T1', bend: false },
  T8: { lower: 'T4', lowerH: 4, upper: 'T1', bend: false },
  T9: { lower: 'T4', lowerH: 2, upper: 'T1', bend: true },
  T10: { lower: 'T10', lowerH: 0, upper: 'T10', bend: false }
};
const PRESET_LABELS = { T1: 'T1 투명+수평선(전체)', T2: 'T2 투명+점무늬(전체)', T3: 'T3 투명+와이어(전체)', T4: 'T4 알루미늄(전체)', T5: 'T5 칼라강판(전체)', T6: 'T6 콘크리트(전체)', T7: 'T7 조합 하부2m+투명', T8: 'T8 조합 하부4m+투명', T9: 'T9 상단 절곡 30°', T10: 'T10 벽면 녹화' };

const HEIGHTS = [...new Set(CFG.wall.heights.map(Number))];
const defPreset = PRESETS[CFG.wall.defaultPreset] ? CFG.wall.defaultPreset : 'T7';
const state = {
  H: HEIGHTS.includes(Number(CFG.wall.defaultHeight)) ? Number(CFG.wall.defaultHeight) : HEIGHTS[0],
  trans: CFG.wall.transmittance,
  arms: { north: { preset: defPreset, ...PRESETS[defPreset] }, east: { preset: defPreset, ...PRESETS[defPreset] } },
  woodPost: false, vineAge: 'new',
  view: 'V1', floor: Math.min(2, VL.n), sun: 'equinox', compare: false, compareView: 'V2'
};

const ARMS = {
  north: { horiz: true, from: 0, to: L.Ln, line: L.wallLine },          // 도로측 = +Y
  east: { horiz: false, from: L.eastTo, to: L.eastFrom, line: L.wallLineX } // 도로측 = +X
};
const qBendN = new THREE.Quaternion().setFromEuler(new THREE.Euler(-30 * DEG, 0, 0));
const qBendE = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, -30 * DEG));
let glassMats = [];
const glassOpacity = () => Math.max(0.05, (1 - state.trans / 100) * 0.8);
function glassMaterial() {
  const g = new THREE.MeshStandardMaterial({ color: 0xe9f3f4, roughness: 0.1, metalness: 0, transparent: true, opacity: glassOpacity(), depthWrite: false });
  glassMats.push(g); return g;
}
function patternMaterial(type, len, h) {
  let t;
  if (type === 'T1') { t = texT1(); t.repeat.set(1, h / 0.05); }
  else { t = texT2(); t.repeat.set(len / 0.1, h / 0.05); }
  return new THREE.MeshBasicMaterial({ color: 0x111111, alphaMap: t, transparent: true, side: THREE.DoubleSide, depthWrite: false });
}
function opaqueMaterial(type, len, h) {
  if (type === 'T5') return mat.t5;
  if (type === 'T6') { const t = texT6(); t.repeat.set(len / 4, h); return new THREE.MeshStandardMaterial({ map: t, roughness: 0.9, side: THREE.DoubleSide }); }
  const t = texT4(); t.repeat.set(len / 0.4, h / 0.4);
  return new THREE.MeshStandardMaterial({ map: t, roughness: 0.65, metalness: 0.15, side: THREE.DoubleSide });
}
function buildArm(group, armKey, cfg, H) {
  const A = ARMS[armKey];
  const len = A.to - A.from, mid = (A.from + A.to) / 2;
  if (len <= 0.5) return;
  const P = (along, off, z) => A.horiz ? [along, A.line + off, z] : [A.line + off, along, z];
  const B = (alongLen, offTh, h, material, along, off, z, opts) => {
    const p = P(along, off, z);
    return A.horiz ? bx(alongLen, offTh, h, material, p[0], p[1], p[2], opts) : bx(offTh, alongLen, h, material, p[0], p[1], p[2], opts);
  };
  group.add(B(len, 0.6, 0.3, mat.concrete, mid, 0, 0.15)); // 기초
  const bend = cfg.bend && H > 3;
  const topZ = H - (bend ? 1.5 : 0);
  // 지주(H형강). 창 시점·단면 절단선이 경간 가운데 오도록 WIN_X 기준으로 배치
  const postMat = (state.woodPost && cfg.upper === 'T3') ? mat.wood : mat.steel;
  const sp = CFG.wall.postSpacing;
  const flanges = [], webs = [];
  const posts = new Set([A.from, A.to]);
  const ref = A.horiz ? WIN_X + sp / 2 : A.to;
  for (let a = ref; a < A.to - 0.5; a += sp) if (a > A.from + 0.5) posts.add(a);
  for (let a = ref - sp; a > A.from + 0.5; a -= sp) if (a < A.to - 0.5) posts.add(a);
  if (armKey === 'east') posts.delete(A.to); // 모서리 지주는 북측 팔이 보유
  for (const a of posts) {
    const mk = (sw, so, h, off, z) => { const pos = P(a, off, z); return A.horiz ? m4(pos[0], pos[1], pos[2], sw, so, h) : m4(pos[0], pos[1], pos[2], so, sw, h); };
    flanges.push(mk(0.3, 0.05, topZ, 0.225, topZ / 2), mk(0.3, 0.05, topZ, -0.225, topZ / 2));
    webs.push(mk(0.06, 0.4, topZ, 0, topZ / 2));
  }
  group.add(inst(flanges, postMat), inst(webs, postMat));
  let glassBot = 0.3;
  if (cfg.lowerH > 0) {
    const h = Math.min(cfg.lowerH, topZ) - 0.3, lt = cfg.lower;
    if (TYPE_INFO[lt].clear) { group.add(B(len, 0.05, h, glassMaterial(), mid, 0, 0.3 + h / 2, { cast: false })); addPattern(group, armKey, lt, len, mid, 0.3, h); }
    else { group.add(B(len, 0.3, h, opaqueMaterial(lt, len, h), mid, 0, 0.3 + h / 2)); if (lt === 'T10') addVine(group, armKey, len, mid, 0.3, h); }
    group.add(B(len, 0.42, 0.12, mat.cap, mid, 0, 0.3 + h + 0.06));
    glassBot = 0.3 + h + 0.12;
  }
  const uh = topZ - glassBot;
  if (uh > 0.2) {
    const ut = cfg.upper;
    if (TYPE_INFO[ut].clear) {
      group.add(B(len, 0.05, uh, glassMaterial(), mid, 0, glassBot + uh / 2, { cast: false }));
      if (ut === 'T3') addWires(group, armKey, len, mid, glassBot, uh); else addPattern(group, armKey, ut, len, mid, glassBot, uh);
    } else {
      group.add(B(len, 0.3, uh, opaqueMaterial(ut, len, uh), mid, 0, glassBot + uh / 2));
      if (ut === 'T10') addVine(group, armKey, len, mid, glassBot, uh);
    }
    const railM = [];
    for (let z = glassBot + 2; z < topZ - 0.4; z += 2) { const p = P(mid, 0, z);
      railM.push(A.horiz ? m4(p[0], p[1], p[2], len, 0.14, 0.09) : m4(p[0], p[1], p[2], 0.14, len, 0.09)); }
    if (railM.length) group.add(inst(railM, mat.cap));
  }
  if (bend) { // 상단 1.5 m를 도로 쪽으로 30° 절곡
    const q = A.horiz ? qBendN : qBendE, co = 0.75;
    group.add(B(len, 0.05, 1.5, TYPE_INFO[cfg.upper].clear ? glassMaterial() : opaqueMaterial(cfg.upper, len, 1.5), mid, co * Math.sin(30 * DEG), topZ + co * Math.cos(30 * DEG), { q, cast: !TYPE_INFO[cfg.upper].clear }));
    group.add(B(len, 0.4, 0.12, mat.cap, mid, 0, topZ + 0.03));
    group.add(B(len, 0.5, 0.22, mat.cap, mid, 1.5 * Math.sin(30 * DEG), topZ + 1.5 * Math.cos(30 * DEG), { q }));
  } else if (H > 0) group.add(B(len, 0.55, 0.22, mat.cap, mid, 0, H - 0.11));
}
function addPattern(group, armKey, type, len, mid, z0, h) {
  const A = ARMS[armKey];
  for (const s of [1, -1]) {
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(len, h), patternMaterial(type, len, h));
    mesh.renderOrder = 2;
    if (A.horiz) mesh.position.copy(W(mid, A.line + s * 0.05, z0 + h / 2));
    else { mesh.rotation.y = Math.PI / 2; mesh.position.copy(W(A.line + s * 0.05, mid, z0 + h / 2)); }
    group.add(mesh);
  }
}
function addWires(group, armKey, len, mid, z0, h) {
  const A = ARMS[armKey], ms = [];
  for (let z = z0 + 0.05; z < z0 + h; z += 0.05) {
    const p = A.horiz ? [mid, A.line + 0.28, z] : [A.line + 0.28, mid, z];
    ms.push(A.horiz ? m4(p[0], p[1], p[2], len, 0.007, 0.007) : m4(p[0], p[1], p[2], 0.007, len, 0.007));
  }
  group.add(inst(ms, mat.wire));
}
function addVine(group, armKey, len, mid, z0, h) {
  const A = ARMS[armKey];
  const t = texVine(state.vineAge === 'old'); t.repeat.set(len / 14, 1);
  const vh = state.vineAge === 'old' ? h * 0.85 : Math.min(h, 2.5);
  const m = new THREE.MeshStandardMaterial({ color: 0x3f5e3c, alphaMap: t, transparent: true, roughness: 1, side: THREE.DoubleSide, depthWrite: false });
  for (const s of [1, -1]) {
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(len, vh), m);
    mesh.renderOrder = 2;
    if (A.horiz) mesh.position.copy(W(mid, A.line + s * 0.17, z0 + vh / 2));
    else { mesh.rotation.y = Math.PI / 2; mesh.position.copy(W(A.line + s * 0.17, mid, z0 + vh / 2)); }
    group.add(mesh);
  }
}
function buildWall(H, armCfgs) {
  const g = new THREE.Group();
  if (H <= 0) return g;
  buildArm(g, 'north', armCfgs.north, H);
  buildArm(g, 'east', armCfgs.east, H);
  return g;
}
function disposeGroup(g) { g.traverse(o => { if (o.geometry && o.geometry !== UNIT) o.geometry.dispose(); }); }
let wallGroup = null;
function rebuildWall() {
  glassMats = [];
  if (wallGroup) { scene.remove(wallGroup); disposeGroup(wallGroup); }
  wallGroup = buildWall(state.H, state.arms);
  wallGroup.visible = !state.compare;
  scene.add(wallGroup);
  cmpDirty = true;
  rebuildSection();
  renderFloorTable();
  document.getElementById('capSub').textContent = state.H > 0
    ? `${CFG.projectName} · ㄱ자 H=${state.H} m (북 ${fmt(L.Ln)} m + 동 ${fmt(L.Le)} m) · 가상 예시`
    : `${CFG.projectName} · 방음벽 미설치 (H=0) · 가상 예시`;
}

/* 비교(2×2) 벽 캐시 */
const CMP_TYPES = ['T1', 'T4', 'T7', 'T9'];
const CMP_LABELS = {
  T1: ['T1 전면 투명 · 수평선', '투과율(추정) 60~70%'],
  T4: ['T4 알루미늄 흡음', '투과율 0%'],
  T7: ['T7 조합 (하부 2m + 투명)', '상부 투과율 65%'],
  T9: ['T9 상단 절곡 30°', '상부 투과율 65%']
};
let cmpWalls = null, cmpDirty = true;
function ensureCmpWalls() {
  if (!cmpDirty && cmpWalls) return;
  if (cmpWalls) for (const w of cmpWalls) { scene.remove(w); disposeGroup(w); }
  cmpWalls = CMP_TYPES.map(t => {
    const g = buildWall(state.H, { north: { ...PRESETS[t] }, east: { ...PRESETS[t] } });
    g.visible = false; scene.add(g); return g;
  });
  cmpDirty = false;
}

/* ================================================================
 * 8. V8 단면 오버레이 (창 → 벽 상단 시선, 가려지는 범위 음영)
 * ================================================================ */
const lineMat = new THREE.LineBasicMaterial({ color: 0x1d1d1f });
const sightMat = new THREE.LineBasicMaterial({ color: 0x0066cc });
let sectionGroup = null;
function textSprite(str, hM, color = '#1d1d1f') {
  const c = document.createElement('canvas'), g = c.getContext('2d');
  const font = '600 46px system-ui, -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif';
  g.font = font;
  const w = Math.ceil(g.measureText(str).width) + 28;
  c.width = w; c.height = 64;
  const g2 = c.getContext('2d');
  g2.font = font; g2.fillStyle = 'rgba(245,245,247,0.85)'; g2.fillRect(0, 0, w, 64);
  g2.fillStyle = color; g2.textBaseline = 'middle'; g2.fillText(str, 14, 34);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false }));
  sp.scale.set(hM * w / 64, hM, 1); sp.renderOrder = 20;
  return sp;
}
const polyline = (pts, m = lineMat) => new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts.map(p => W(p[0], p[1], p[2]))), m);
function sectionFloors() {
  const n = VL.n, s = new Set([1, Math.ceil(n / 2), n]);
  return [...s].filter(f => f >= 1);
}
function rebuildSection() {
  if (sectionGroup) { scene.remove(sectionGroup); disposeGroup(sectionGroup); }
  sectionGroup = new THREE.Group();
  const X = CUT_X - 0.5, H = state.H, Yw = L.wallLine, Yn = L.Yn, Wm = L.Wm;
  const add = o => sectionGroup.add(o);
  const label = (str, y, z, h = 1.7, color) => { const s = textSprite(str, h, color); s.position.copy(W(X, y, z)); add(s); };
  add(polyline([[X, Yn, 2.2], [X, Yn + Wm, 2.2]])); add(polyline([[X, Yn, 0.2], [X, Yn, 3]])); add(polyline([[X, Yn + Wm, 0.2], [X, Yn + Wm, 3]]));
  label(`도로 ${fmt(Wm)} m`, Yn + Wm / 2, 3.6);
  add(polyline([[X, facadeY, 1.2], [X, Yw, 1.2]]));
  label(`이격 ${fmt(L.setback)} m`, (facadeY + Yw) / 2, 2.6, 1.3);
  add(polyline([[X, facadeY - 3.8, 0], [X, facadeY - 3.8, VL.eave]])); add(polyline([[X, facadeY - 4.7, VL.eave], [X, facadeY, VL.eave]]));
  label(`건물 ${fmt(VL.eave)} m`, facadeY - 6.2, VL.eave / 2);
  if (H > 0) {
    add(polyline([[X, Yw + 3.2, 0], [X, Yw + 3.2, H]])); add(polyline([[X, Yw + 0.3, H], [X, Yw + 4.1, H]]));
    label(`방음벽 ${H} m`, Yw + 6.3, H / 2);
    const shadeM = new THREE.MeshBasicMaterial({ color: 0x1d1d1f, transparent: true, opacity: 0.1, side: THREE.DoubleSide, depthWrite: false });
    const d = Yw - facadeY;
    const zCap = Math.max(H + 20, 40), yFar = Yn + Wm + 22;
    for (const f of sectionFloors()) {
      const zw = eyeZ(f);
      if (zw >= H) continue;
      const slope = (H - zw) / d;
      const zAtFar = H + slope * (yFar - Yw);
      const ray = [[X, facadeY, zw], [X, Yw, H]];
      ray.push(zAtFar <= zCap ? [X, yFar, zAtFar] : [X, Yw + (zCap - H) / slope, zCap]);
      add(polyline(ray, sightMat));
      label(`${f}F`, facadeY - 0.9, zw, 1.2, '#0066cc');
      const pts2 = [[Yw, 0], [Yw, H]];
      if (zAtFar <= zCap) pts2.push([yFar, zAtFar]); else pts2.push([Yw + (zCap - H) / slope, zCap], [yFar, zCap]);
      pts2.push([yFar, 0]);
      const shape = new THREE.Shape();
      shape.moveTo(-pts2[0][0], pts2[0][1]);
      for (let i = 1; i < pts2.length; i++) shape.lineTo(-pts2[i][0], pts2[i][1]);
      const sg = new THREE.ShapeGeometry(shape); sg.rotateY(-Math.PI / 2);
      const sm = new THREE.Mesh(sg, shadeM); sm.position.set(X - 0.3, 0, 0); sm.renderOrder = 15;
      add(sm);
    }
  }
  sectionGroup.visible = (state.view === 'V8');
  scene.add(sectionGroup);
}

/* ================================================================
 * 9. 층별 창 시야 표 (층고 환산)
 * ================================================================ */
function floorRows() {
  const fa = CFG.floorAnalysis, rows = [];
  for (let f = 1; f <= fa.maxFloor; f++) {
    const base = (f - 1) * VL.fh, eye = base + fa.eyeHeight, diff = eye - state.H;
    rows.push({ f, base, eye, diff, open: state.H <= 0 || diff > 0, noise: fa.noiseByFloor ? fa.noiseByFloor[f] : undefined });
  }
  return rows;
}
function firstOpenFloor() {
  if (state.H <= 0) return 1;
  return Math.floor((state.H - CFG.floorAnalysis.eyeHeight) / VL.fh) + 2;
}
function renderFloorTable() {
  const rows = floorRows();
  const hasNoise = rows.some(r => r.noise !== undefined);
  let h = `<table class="floors"><tr><th>층</th><th>바닥</th><th>눈높이</th><th>벽 상단 대비</th><th>창밖</th>${hasNoise ? '<th>소음</th>' : ''}</tr>`;
  for (const r of rows.slice().reverse()) {
    const rel = state.H <= 0 ? '-' : (r.diff > 0 ? `위 ${fmt(r.diff)} m` : `아래 ${fmt(-r.diff)} m`);
    const cls = [r.open ? 'open' : '', r.f === state.floor && r.f <= VL.n ? 'sel' : ''].join(' ');
    h += `<tr class="${cls}" data-f="${r.f}"><td>${r.f}F${r.f > VL.n ? '*' : ''}</td><td>${fmt(r.base)}</td><td>${fmt(r.eye)}</td><td>${rel}</td><td>${r.open ? '바깥 보임' : '벽면만'}</td>${hasNoise ? `<td>${r.noise ?? '-'}</td>` : ''}</tr>`;
  }
  h += '</table>';
  document.getElementById('floorTable').innerHTML = h;
  const k = firstOpenFloor();
  document.getElementById('floorNote').innerHTML = state.H <= 0 ? '방음벽 미설치 상태입니다.'
    : `층고 ${VL.fh} m 환산, 눈높이 바닥 + ${CFG.floorAnalysis.eyeHeight} m. <b>${k}층</b>부터 벽 상단(${state.H} m) 너머가 보입니다. `
      + `* 표시는 모델 건물(${VL.n}층)보다 높은 가상 층입니다.${hasNoise ? ' 소음 열은 config.js의 가상값입니다.' : ''}`;
}
document.getElementById('floorTable').addEventListener('click', e => {
  const tr = e.target.closest('tr[data-f]'); if (!tr) return;
  const f = Number(tr.dataset.f); if (f > VL.n) return;
  state.floor = f; document.getElementById('floorSel').value = String(f);
  if (state.compare) exitCompare();
  setView('V4'); renderFloorTable();
});

/* ================================================================
 * 10. 격자 · 시점
 * ================================================================ */
const gridSize = Math.ceil((L.eastEdge + 300) / 100) * 100;
const grid = new THREE.GridHelper(gridSize, gridSize / 10, 0x9aa0a6, 0xc4c8cc);
grid.position.copy(W(L.cx, L.cy, 0.16));
grid.material.transparent = true; grid.material.opacity = 0.5;
scene.add(grid);

function views() {
  const span = Math.max(L.eastEdge, L.northEdge);
  const pedX = villaCols[0] + VL.w + VL.gap / 2;
  return {
    V1: { name: 'V1 조감', eye: [L.cx, L.cy - span * 0.9, span * 0.62], look: [L.cx, L.cy, 0] },
    V2: { name: 'V2 벽 뒤 보행자', eye: [pedX, L.wallLine - 6, 1.5], look: [pedX, L.wallLine + 60, 1.5] },
    V3: { name: 'V3 동측 소로 보행자', eye: [L.Xv + L.Wl / 2, L.wallLine - 6, 1.5], look: [L.Xv + L.Wl / 2 - 60, L.wallLine - 6, 1.5] },
    V4: { name: `V4 벽 뒤 건물 ${state.floor}층 창`, eye: [WIN_X, facadeY - 0.5, eyeZ(state.floor)], look: [WIN_X, facadeY + 60, eyeZ(state.floor)] },
    V6: officeTopEye.ok
      ? { name: `V6 업무 ${CFG.office.floors}층 창`, eye: [officeTopEye.x, officeTopEye.y, officeTopEye.z], look: [officeTopEye.x + 60, officeTopEye.y, officeTopEye.z] }
      : { name: 'V6 업무층(건물 없음)', eye: [L.Ln - 10, L.cy, 20], look: [L.Ln + 60, L.cy, 20] },
    V7: { name: 'V7 북측 도로 운전자', eye: [L.Ln * 0.6, L.Yn + L.Wm * 0.5, 1.2], look: [L.Ln * 0.6 - 70, L.Yn + L.Wm * 0.5, 1.2] },
    V8: { name: `V8 단면 (정사영 · 절단 X=${fmt(CUT_X)} · 남→북)` }
  };
}
let VIEWS = views();
function setView(v) {
  state.view = v; VIEWS = views();
  document.querySelectorAll('#viewBtns .pill').forEach(b => b.classList.toggle('on', b.dataset.v === v));
  if (sectionGroup) sectionGroup.visible = (v === 'V8');
  if (v === 'V8') {
    activeCam = orthoCam;
    controls.enabled = false; controlsO.enabled = true;
    const halfH = Math.max(26, state.H * 0.9 + 8, VL.eave * 0.9 + 8), halfW = halfH * viewW / viewH;
    orthoCam.left = -halfW; orthoCam.right = halfW; orthoCam.top = halfH; orthoCam.bottom = -halfH;
    const camX = CUT_X + 152;
    orthoCam.near = 152; orthoCam.far = 152 + CUT_X + 200; orthoCam.zoom = 1;
    const cy = L.Yn - 4, cz = halfH * 0.7;
    orthoCam.position.copy(W(camX, cy, cz));
    orthoCam.updateProjectionMatrix();
    controlsO.target.copy(W(0, cy, cz));
    orthoCam.lookAt(controlsO.target);
    controlsO.update();
  } else {
    activeCam = cam;
    controls.enabled = !state.compare; controlsO.enabled = false;
    const V = VIEWS[v];
    cam.position.copy(W(...V.eye));
    controls.target.copy(W(...V.look));
    controls.update();
  }
}

/* ================================================================
 * 11. 패널 배선
 * ================================================================ */
{
  const hSeg = document.getElementById('hSeg');
  hSeg.innerHTML = HEIGHTS.map(h => `<button data-h="${h}" class="${h === state.H ? 'on' : ''}">${h}</button>`).join('');
  hSeg.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    hSeg.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    state.H = Number(b.dataset.h); rebuildWall();
  });
  const fs = document.getElementById('floorSel');
  fs.innerHTML = Array.from({ length: VL.n }, (_, i) => `<option value="${i + 1}">${i + 1}층 (눈높이 ${fmt(eyeZ(i + 1))} m)</option>`).join('');
  fs.value = String(state.floor);
  fs.addEventListener('change', () => { state.floor = Number(fs.value); renderFloorTable(); if (state.view === 'V4') setView('V4'); });
  const ts = document.getElementById('transSlider');
  ts.value = state.trans; document.getElementById('transVal').textContent = state.trans + '%';
  ts.addEventListener('input', () => {
    state.trans = Number(ts.value);
    document.getElementById('transVal').textContent = state.trans + '%';
    const op = glassOpacity(); for (const g of glassMats) g.opacity = op;
    cmpDirty = true;
  });
}
function armCard(el, key, title) {
  el.innerHTML = `<div class="ttl">${title}</div>
    <div class="row"><label>유형 프리셋</label><select data-k="preset">${Object.keys(PRESETS).map(t => `<option value="${t}">${PRESET_LABELS[t]}</option>`).join('')}<option value="custom">사용자 조합</option></select></div>
    <div class="row"><label>하단부 높이</label><select data-k="lowerH"><option value="0">0 m (없음)</option><option value="2">2 m</option><option value="4">4 m</option></select></div>
    <div class="row"><label>하단부 유형</label><select data-k="lower">${Object.keys(TYPE_INFO).map(t => `<option value="${t}">${TYPE_INFO[t].label}</option>`).join('')}</select></div>
    <div class="row"><label>상단부 유형</label><select data-k="upper">${Object.keys(TYPE_INFO).map(t => `<option value="${t}">${TYPE_INFO[t].label}</option>`).join('')}</select></div>
    <div class="row"><label>상단 절곡 30° (T9)</label><input type="checkbox" data-k="bend"></div>
    <div class="est" data-k="est"></div>`;
  const cfg = state.arms[key];
  const sync = () => {
    el.querySelector('[data-k=preset]').value = cfg.preset;
    el.querySelector('[data-k=lowerH]').value = String(cfg.lowerH);
    el.querySelector('[data-k=lower]').value = cfg.lower;
    el.querySelector('[data-k=upper]').value = cfg.upper;
    el.querySelector('[data-k=bend]').checked = cfg.bend;
    el.querySelector('[data-k=est]').textContent =
      `가시광 투과율(추정): 상단 ${TYPE_INFO[cfg.upper].trans}${cfg.lowerH > 0 ? ` · 하단 ${TYPE_INFO[cfg.lower].trans}` : ''}`;
  };
  el.addEventListener('change', e => {
    const k = e.target.dataset.k;
    if (k === 'preset') { if (e.target.value !== 'custom') Object.assign(cfg, { preset: e.target.value }, PRESETS[e.target.value]); }
    else {
      if (k === 'bend') cfg.bend = e.target.checked;
      else if (k === 'lowerH') cfg.lowerH = Number(e.target.value);
      else cfg[k] = e.target.value;
      cfg.preset = 'custom';
    }
    sync(); rebuildWall();
  });
  sync();
}
armCard(document.getElementById('armN'), 'north', `북측 팔 · Y=${fmt(L.wallLine)} · X 0→${fmt(L.Ln)} (${fmt(L.Ln)} m)`);
armCard(document.getElementById('armE'), 'east', `동측 팔 · X=${fmt(L.wallLineX)} · Y ${fmt(L.eastFrom)}→${fmt(L.eastTo)} (${fmt(L.Le)} m)`);

document.getElementById('woodPost').addEventListener('change', e => { state.woodPost = e.target.checked; rebuildWall(); });
document.getElementById('vineSeg').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  document.querySelectorAll('#vineSeg button').forEach(x => x.classList.toggle('on', x === b));
  state.vineAge = b.dataset.a; rebuildWall();
});
document.getElementById('viewBtns').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  if (state.compare) exitCompare();
  setView(b.dataset.v);
});
document.getElementById('sunBtns').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  document.querySelectorAll('#sunBtns .pill').forEach(x => x.classList.toggle('on', x === b));
  setSun(b.dataset.s);
});
document.getElementById('gridChk').addEventListener('change', e => { grid.visible = e.target.checked; });
document.getElementById('villaChk').addEventListener('change', e => { villaGroup.visible = e.target.checked; });
{
  const dlg = document.getElementById('assumeDlg');
  const r = CFG.roads;
  document.getElementById('assumeList').innerHTML = [
    `방음벽 ㄱ자: 북측 팔 ${fmt(L.Ln)} m + 동측 팔 ${fmt(L.Le)} m, 높이 대안 ${HEIGHTS.join(' / ')} m`,
    `지주 간격 ${CFG.wall.postSpacing} m(가정) · 투과율 기본 ${CFG.wall.transmittance}%`,
    `북측 도로 ${r.north.width} m(${r.north.lanes}차로) · 동측 도로 ${r.east.width} m(${r.east.lanes}차로) · 소로 ${r.local.width} m · 보도 편측 ${r.sidewalk} m`,
    `벽 위치 = 필지 경계선(도로 경계) · 건물 외벽까지 이격 ${L.setback} m`,
    `벽 뒤 건물 ${VL.n}층(${VL.piloti ? '1층 필로티, ' : ''}층고 ${VL.fh} m, 난간 ${VL.parapet} m, 처마 ${fmt(VL.eave)} m)`,
    `업무 ${CFG.office.floors}층(층고 ${CFG.office.floorHeight} m) · 연구 ${CFG.research.floors}층(층고 ${CFG.research.floorHeight} m)`,
    `앙각·거리는 눈 위치 기준. 태양 고도는 위도 ${LAT}° 계산값: 동지 정오 ${fmt(SUNS.winter.el)}° · 춘분 정오 ${fmt(SUNS.equinox.el)}° · 하지 정오 ${fmt(SUNS.summer.el)}° · 춘분 오후 3시 ${fmt(SUNS.pm3.el)}°`,
    '지반 평탄(Z=0) · 가로수·농가·비닐하우스는 맥락 표현(치수 비기준)'
  ].map(s => `<li>${s}</li>`).join('');
  document.getElementById('sourceList').innerHTML = (CFG.sources || []).map(s => `<li>${s}</li>`).join('');
  document.getElementById('assumeBtn').addEventListener('click', () => dlg.showModal());
  document.getElementById('assumeClose').addEventListener('click', () => dlg.close());
}

/* ================================================================
 * 12. 비교 모드
 * ================================================================ */
const cmpBtn = document.getElementById('cmpBtn');
const cmpOverlay = document.getElementById('cmpOverlay');
const cmpCam = new THREE.PerspectiveCamera(55, 1, 0.1, 4000);
function enterCompare() {
  state.compare = true;
  ensureCmpWalls();
  wallGroup.visible = false;
  controls.enabled = false; controlsO.enabled = false;
  cmpOverlay.style.display = 'block';
  document.getElementById('caption').style.display = 'none';
  cmpBtn.textContent = '비교 닫기';
  document.getElementById('cmpViewRow').style.display = 'flex';
  CMP_TYPES.forEach((t, i) => { document.getElementById('cl' + i).innerHTML = `${CMP_LABELS[t][0]} <span>· ${CMP_LABELS[t][1]}</span>`; });
}
function exitCompare() {
  state.compare = false;
  if (cmpWalls) cmpWalls.forEach(w => { w.visible = false; });
  wallGroup.visible = true;
  cmpOverlay.style.display = 'none';
  document.getElementById('caption').style.display = '';
  cmpBtn.textContent = 'T1 · T4 · T7 · T9 비교';
  document.getElementById('cmpViewRow').style.display = 'none';
  setView(state.view === 'V8' ? 'V1' : state.view);
}
cmpBtn.addEventListener('click', () => (state.compare ? exitCompare() : enterCompare()));
document.getElementById('cmpViewSeg').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  document.querySelectorAll('#cmpViewSeg button').forEach(x => x.classList.toggle('on', x === b));
  state.compareView = b.dataset.cv;
});

/* ================================================================
 * 13. 크기 · 루프 · 판독
 * ================================================================ */
let viewW = 2, viewH = 2;
function resize() {
  viewW = stageEl.clientWidth; viewH = stageEl.clientHeight;
  renderer.setSize(viewW, viewH);
  cam.aspect = viewW / viewH; cam.updateProjectionMatrix();
  if (state.view === 'V8') setView('V8');
}
addEventListener('resize', resize);

const bottombar = document.getElementById('bottombar');
const arrow = document.getElementById('compassArrow');
function wallDistance(x, y) {
  const cx = Math.max(0, Math.min(L.Ln, x));
  const dN = Math.hypot(x - cx, y - L.wallLine);
  const cy = Math.max(L.eastTo, Math.min(L.eastFrom, y));
  const dE = L.Le > 0 ? Math.hypot(x - L.wallLineX, y - cy) : Infinity;
  return Math.min(dN, dE);
}
function readout() {
  const p = activeCam.position;
  const ex = p.x, ey = -p.z, ez = p.y;
  const sunL = SUNS[state.sun].label;
  if (state.compare) {
    bottombar.innerHTML = `<b>유형 비교</b><span class="sep">·</span>시점 ${state.compareView === 'V2' ? 'V2 보행자' : `V4 ${state.floor}층 창`}<span class="sep">·</span>H=${state.H} m · 태양 ${sunL}`;
    return;
  }
  if (state.view === 'V8') {
    bottombar.innerHTML = `<b>V8 단면(정사영)</b><span class="sep">·</span>절단 X=${fmt(CUT_X)} · 남→북<span class="sep">·</span>검산: 도로 ${fmt(L.Wm)} · 벽 ${state.H} · 이격 ${fmt(L.setback)} · 건물 ${fmt(VL.eave)}`;
    return;
  }
  let wallTxt;
  if (state.H <= 0) wallTxt = '방음벽 미설치';
  else {
    const d = wallDistance(ex, ey), ang = Math.atan2(state.H - ez, d) / DEG;
    wallTxt = `벽까지 수평거리 <b>${fmt(d)} m</b><span class="sep">·</span>벽 상단(${state.H} m) 앙각 <b>${fmt(ang)}°</b>`;
  }
  bottombar.innerHTML = `<b>${VIEWS[state.view].name}</b><span class="sep">·</span>${wallTxt}<span class="sep">·</span>태양 ${sunL}`;
}
function compass() {
  const d = new THREE.Vector3(); activeCam.getWorldDirection(d);
  arrow.style.transform = `rotate(${-Math.atan2(d.x, -d.z) / DEG}deg)`;
}
function renderCompare() {
  ensureCmpWalls();
  const V = VIEWS[state.compareView];
  cmpCam.aspect = viewW / viewH; cmpCam.updateProjectionMatrix();
  cmpCam.position.copy(W(...V.eye)); cmpCam.lookAt(W(...V.look));
  renderer.setScissorTest(true);
  const q = [[0, viewH / 2], [viewW / 2, viewH / 2], [0, 0], [viewW / 2, 0]];
  CMP_TYPES.forEach((t, i) => {
    cmpWalls.forEach((w, j) => { w.visible = (j === i); });
    renderer.setViewport(q[i][0], q[i][1], viewW / 2, viewH / 2);
    renderer.setScissor(q[i][0], q[i][1], viewW / 2, viewH / 2);
    renderer.render(scene, cmpCam);
  });
  cmpWalls.forEach(w => { w.visible = false; });
  renderer.setScissorTest(false);
  renderer.setViewport(0, 0, viewW, viewH);
}
function frame() {
  controls.update(); controlsO.update();
  if (state.compare) renderCompare(); else renderer.render(scene, activeCam);
  readout(); compass();
}
function animate() { requestAnimationFrame(animate); frame(); }

/* 시작 */
window.__dbg = { state, L, VL, cam, controls, W, setView, setSun, rebuildWall, enterCompare, exitCompare, render: frame, floorRows, firstOpenFloor };
setSun('equinox');
rebuildWall();
resize();
setView('V1');
animate();
