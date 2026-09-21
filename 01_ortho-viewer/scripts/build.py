#!/usr/bin/env python3
"""평면 현황지도(평면지도.html)를 만든다

  python3 scripts/build.py --config sample_data/config.json

  ㅇ 바탕 = 정사영상 타일({output_dir}/tiles). 음영기복 타일({output_dir}/hs)을 겹쳐 밭두렁·구거·단차를 드러낸다
  ㅇ 사업지구 경계·블록, 현황 건물·도로·구거, 등고선, 지적을 단추로 켜고 끈다
  ㅇ 지도를 누르면 지반고·표면고와 평면직각좌표(기본 EPSG:5186). 거리·면적 재기 포함
  ㅇ 여는 법: {output_dir}/평면지도.html 더블클릭. 서버도 인터넷도 필요 없다
    (라이브러리·자료·표고 격자를 모두 화면 파일 안에 담는다. file:// 에서는 fetch 가 막히기 때문)

읽는 자료(없으면 그 단추만 비고 나머지는 돈다)
  {data_dir}/base.json        bounds · 구역계(GeoJSON Feature 목록) · 블록(FeatureCollection)
  {data_dir}/현황건물.json     {"선": [[[lon,lat],...], ...]}
  {data_dir}/도로.json · 구거.json   같은 모양
  {data_dir}/등고선.json       {"선": [{"h":표고,"p":[[lon,lat],...]}], "표": [{"h","p":[lon,lat],"a":각도}]}
  {data_dir}/지적.json         {"기준": {...}, "필지": [{"p","c","j"(지번),"m"(지목),"s"(넓이),"o"(국/공/사),...}]}
  {work_dir}/dem.json · 지반고.json   표고 격자(tiles_nogdal.py 또는 build_dsm.sh 가 만든다)

⚠ 대외 공개 주의: 고해상도 정사영상은 남의 집 마당·차량까지 보인다. 실자료로 만든 화면은 인터넷에 올리지 않는다.
필요 패키지: 표준 라이브러리만
"""
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import config  # noqa: E402

TEMPLATE = """<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=5">
<meta name="theme-color" content="#1b1d1f">
<title>/*__TITLE__*/(평면)</title>
<style>/*__LEAFLET_CSS__*/</style>
<style>
:root{--bg:#1b1d1f;--ink:#f2f4f6;--sub:#a8b0b8;--line:#33373b;--accent:#00d0a4;
  --safe-t:env(safe-area-inset-top,0px);--safe-b:env(safe-area-inset-bottom,0px)}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
#map{position:absolute;inset:0;background:#111}
.leaflet-container{background:#111}
.bar{position:absolute;left:0;right:0;top:0;z-index:900;padding:calc(var(--safe-t) + 8px) 12px 8px;
  background:linear-gradient(#1b1d1fee,#1b1d1f00);pointer-events:none}
.bar b{font-size:.95em}
.bar span{color:var(--sub);font-size:.8em;margin-left:8px}
.fab.jump{background:#1f5f52ee;border-color:#2f8d78;color:#d8fff5}
.fabs{position:absolute;left:10px;top:calc(var(--safe-t) + 48px);z-index:900;
  display:flex;flex-direction:column;gap:8px}
.fab{background:#2a2e32ee;color:var(--ink);border:1px solid var(--line);border-radius:999px;
  padding:9px 14px;font-size:.85em;font-weight:600;cursor:pointer;min-height:40px;
  box-shadow:0 2px 8px rgba(0,0,0,.4)}
.fab.on{background:var(--accent);color:#08221c;border-color:var(--accent)}
.foot{position:absolute;left:0;right:0;bottom:0;z-index:900;
  padding:8px 12px calc(var(--safe-b) + 8px);color:var(--sub);font-size:.72em;line-height:1.45;
  background:linear-gradient(#1b1d1f00,#1b1d1fdd);pointer-events:none}
.card{position:absolute;left:10px;right:10px;bottom:calc(var(--safe-b) + 46px);z-index:950;
  background:#24282cf5;border:1px solid var(--line);border-radius:12px;padding:12px 14px;
  display:none;max-width:380px;box-shadow:0 4px 20px rgba(0,0,0,.5)}
.card h3{margin:0 0 4px;font-size:1em}
.card .kv{color:var(--sub);font-size:.84em;font-variant-numeric:tabular-nums}
.card .x{position:absolute;right:6px;top:4px;background:none;border:0;color:var(--sub);
  font-size:20px;cursor:pointer;padding:4px 8px}
.cont-label{font-size:10px;font-weight:700;color:#e8ffc4;text-shadow:0 0 3px #000,0 0 3px #000;
  pointer-events:none;white-space:nowrap;font-variant-numeric:tabular-nums;text-align:center}
.cad-label{font-size:10px;font-weight:700;color:#fff;text-shadow:0 0 3px #000,0 0 3px #000;
  pointer-events:none;white-space:nowrap;font-variant-numeric:tabular-nums;text-align:center}
.card .warn{color:#ffd166}
.card .old{color:#8e9aa6;font-size:.92em}
.blk-label{font-size:11px;font-weight:700;color:#fff;text-shadow:0 0 3px #000,0 0 3px #000;
  pointer-events:none;text-align:center}
.card b{color:var(--ink)}
.card .btns{margin-top:9px;display:flex;gap:6px}
.card .btns button{background:#2a2e32;color:var(--ink);border:1px solid var(--line);
  border-radius:8px;padding:5px 11px;font-size:.82em;cursor:pointer}
</style></head><body>
<div id="map"></div>
<div class="bar"><b>/*__TITLE__*/</b><span>/*__SUBTITLE__*/</span></div>
<div class="fabs">
  <button class="fab jump" onclick="location.href=koURL('./입체지도.html')">입체로 &rsaquo;</button>
  <button class="fab" id="bFit">전체</button>
  <button class="fab on" id="bLine">경계</button>
  <button class="fab" id="bHs">음영</button>
  <button class="fab" id="bBldg">건물</button>
  <button class="fab" id="bRw">도로·구거</button>
  <button class="fab" id="bCad">지적</button>
  <button class="fab" id="bTerr">지형</button>
  <button class="fab" id="bMeas">측정</button>
</div>
<div class="card" id="card"><button class="x" id="cardX">&times;</button><div id="cardIn"></div></div>
<div class="foot">/*__FOOTER__*/ · 판 /*__BUILD__*/
<br>/*__GROUND_NOTE__*/ · /*__SURFACE_NOTE__*/. 표고는 지반고가 아닐 수 있습니다(표면은 나무·건물 높이 포함)
<br>지적: <b style="color:#ffd166">국유지</b> · <b style="color:#c77dff">공유지</b> ·
<b style="color:#e6ecf2">사유지</b> · /*__CAD_NOTE__*/</div>

<script>
/* 윈도우 대비 탐침: 맥이 USB(exFAT)에 쓰면 한글 이름이 NFD 로 바뀐다. 윈도우는 바이트가
   같아야 찾으므로, 한글 이름 파일(한글확인.js)이 열리는 형태를 보고 링크 형태를 정한다 */
var KO_NFD=false;
(function(){var s=document.createElement('script');s.src='./\ud55c\uae00\ud655\uc778.js';
  s.onerror=function(){KO_NFD=true;};document.head.appendChild(s);})();
function koURL(p){return KO_NFD? p.normalize('NFD'):p;}
</script>
<script>/*__LEAFLET_JS__*/</script>
<script>
const D = /*__DATA__*/;
const BOUNDS = L.latLngBounds(D.bounds);

const map = L.map('map', {
  minZoom: D.zoom[0], maxZoom: D.zoom[1] + 1,
  zoomSnap: 0,              // 배율을 단계로 끊지 않는다
  zoomDelta: 1,             // +·- 단추는 한 단계씩
  scrollWheelZoom: false,   // 아래에서 직접 처리
  zoomAnimation: true, markerZoomAnimation: true, fadeAnimation: true,
  maxBounds: BOUNDS.pad(0.35), maxBoundsViscosity: 1.0,
  zoomControl: false, attributionControl: false,
  inertia: true, inertiaDeceleration: 2400
});

/* 휠·트랙패드 확대를 손끝에 붙여 따라가게 한다 */
(function smoothWheel() {
  const el = map.getContainer();
  let target = null, anchor = null, raf = null, fallback = null;

  el.addEventListener('wheel', e => {
    e.preventDefault();
    // deltaMode 1 은 줄 단위, 0 은 픽셀 단위로 들어온다
    const px = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
    // 숫자를 키우면 둔해지고 줄이면 예민해진다. 감도는 이 한 곳만 고치면 된다
    const step = -px / 200;
    const base = target === null ? map.getZoom() : target;
    target = Math.max(map.getMinZoom(), Math.min(map.getMaxZoom(), base + step));
    anchor = map.mouseEventToContainerPoint(e);
    if (!raf) {
      raf = requestAnimationFrame(tick);
      // 화면 갱신이 멈춘 곳에서는 위 호출이 오지 않는다. 그때도 반영되도록 뒤늦게 한 번에 옮긴다
      fallback = setTimeout(flush, 200);
    }
  }, { passive: false });

  function tick() {
    if (fallback) { clearTimeout(fallback); fallback = null; }
    const cur = map.getZoom();
    const gap = target - cur;
    if (Math.abs(gap) < 0.004) { raf = null; target = null; return; }
    // 남은 거리의 일부만 좁혀 나가면 시작은 빠르고 끝은 부드럽다
    hsPause();
    map.setZoomAround(map.containerPointToLatLng(anchor), cur + gap * 0.3, { animate: false });
    raf = requestAnimationFrame(tick);
  }

  function flush() {
    fallback = null;
    if (raf) { cancelAnimationFrame(raf); raf = null; }
    if (target !== null && anchor) {
      map.setZoomAround(map.containerPointToLatLng(anchor), target, { animate: false });
    }
    target = null;
  }
})();
// 타일은 설정의 ortho_zoom 범위로 만들었다. 그보다 더 당기면 마지막 배율 타일을 늘려 보여 준다
L.tileLayer('./tiles/{z}/{x}/{y}.jpg', {
  minZoom: D.zoom[0], maxZoom: D.zoom[1] + 1, minNativeZoom: D.zoom[0], maxNativeZoom: D.zoom[1],
  bounds: BOUNDS, tileSize: 256,
  // 확대·축소 중에도 타일을 계속 갱신한다. false 로 두면 옛 타일을 버린 뒤
  // 새 타일이 오기 전까지 바닥(검정)이 드러난다. 타일이 내 PC 안에 있어 갱신이 싸다
  updateWhenZooming: true,
  keepBuffer: 4
}).addTo(map);

/* 음영기복: DSM 으로 만든 그늘을 정사영상 위에 겹친다.
   평지로 보이던 밭두렁·구거·단차가 드러난다. 배율은 설정의 hs_zoom 범위.
   그늘을 과장하고(hs_z_factor) 계조를 늘려 두었다(중립 128). 그냥 곱하면 계조 폭이 좁아 보이지 않는다 */
map.createPane('hs');
Object.assign(map.getPane('hs').style, { zIndex: 250, pointerEvents: 'none' });
const hs = L.tileLayer('./hs/{z}/{x}/{y}.jpg', {
  pane: 'hs', minZoom: D.zoom[0], maxZoom: D.zoom[1] + 1, minNativeZoom: D.hsZoom[0], maxNativeZoom: D.hsZoom[1],
  bounds: BOUNDS, tileSize: 256,
  // 확대·축소 중에는 음영을 감춰 두므로(hsPause) 그동안 타일을 받을 까닭이 없다.
  // 정사영상 쪽은 반대로 true 여야 한다. 감추지 않으므로 바닥이 드러난다
  updateWhenZooming: false, keepBuffer: 2
});
// 0 끔 · 1 연하게 · 2 진하게 · 3 음영만(영상을 가림)
const HS = [null,
  { name: '음영 연하게', blend: 'soft-light', op: 0.9 },
  { name: '음영 진하게', blend: 'overlay',    op: 0.95 },
  { name: '음영만',      blend: 'normal',     op: 1 }];
let hsLv = 0;
function setHs(lv) {
  hsLv = lv;
  const b = document.getElementById('bHs');
  const pane = map.getPane('hs');
  b.classList.toggle('on', lv > 0);
  b.textContent = lv === 0 ? '음영' : HS[lv].name;
  pane.style.display = '';
  if (lv === 0) {
    if (map.hasLayer(hs)) map.removeLayer(hs);
    // ⚠ 합성 방식을 반드시 되돌린다. 빈 계층이라도 걸려 있으면
    //   화면 전체를 매 프레임 다시 섞느라 확대가 뻑뻑해진다
    pane.style.mixBlendMode = 'normal';
    return;
  }
  pane.style.mixBlendMode = HS[lv].blend;
  hs.setOpacity(HS[lv].op);
  if (!map.hasLayer(hs)) hs.addTo(map);
}

/* 확대·축소가 도는 동안에는 음영을 잠시 감춘다.
   두 겹을 매 프레임 섞으면 손끝을 못 따라온다. 멈추면 곧바로 되돌아온다 */
let hsTimer = null;
function hsPause() {
  if (hsLv === 0) return;
  const pane = map.getPane('hs');
  if (pane.style.display !== 'none') pane.style.display = 'none';
  if (hsTimer) clearTimeout(hsTimer);
  hsTimer = setTimeout(() => {
    hsTimer = null;
    if (hsLv > 0) { pane.style.display = ''; }
  }, 140);
  // ⚠ 여기서 hs.redraw() 를 부르면 안 된다. zoomSnap:0 이라 배율이 소수인데
  //    리플릿 redraw() 는 그 값을 반올림하지 않아 `hs/18.4/…` 같은 주소를 요청한다
}
map.on('zoomstart zoom', hsPause);

/* 높이 격자 두 벌. 화면 파일 안에 담아 두었다(file:// 에서는 fetch 가 막힌다). 인터넷 없이 동작한다.
   표면 = DSM(나무·건물 지붕 포함) · 지반 = 지면 표고(있을 때만) */
function loadGrid(d) {
  if (!d) return null;
  const bin = atob(d.b64), buf = new ArrayBuffer(bin.length), u8 = new Uint8Array(buf);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return { w: d.w, h: d.h, x0: d.x0, y0: d.y0, res: d.res, v: new Int16Array(buf) };
}
const DEM = loadGrid(D.dem), GND = loadGrid(D['지반']);
function at(G, ll) {              // 높이(m). 자료 밖이면 null
  if (!G) return null;
  const p = L.Projection.SphericalMercator.project(ll);
  const c = (p.x - G.x0) / G.res, r = (G.y0 - p.y) / G.res;
  if (!(c >= 0 && r >= 0 && c <= G.w - 1 && r <= G.h - 1)) return null;
  const c0 = Math.floor(c), r0 = Math.floor(r), fx = c - c0, fy = r - r0;
  const g = (rr, cc) => {
    const v = G.v[Math.min(G.h - 1, rr) * G.w + Math.min(G.w - 1, cc)];
    return v === -32768 ? null : v / 10;
  };
  const q = [g(r0, c0), g(r0, c0 + 1), g(r0 + 1, c0), g(r0 + 1, c0 + 1)];
  const ok = q.filter(x => x !== null);
  if (!ok.length) return null;
  if (ok.length < 4) return ok[0];       // 가장자리는 이웃값으로 갈음
  return (q[0] * (1 - fx) + q[1] * fx) * (1 - fy) + (q[2] * (1 - fx) + q[3] * fx) * fy;
}
const elev = ll => at(DEM, ll);   // 표면
const gelev = ll => at(GND, ll);  // 지반

/* 평면직각좌표(기본 EPSG:5186 중부원점). 도면 좌표와 맞춰 보기 위한 것.
   원점·가산값은 설정의 crs 항목에서 온다. KGD2002 는 WGS84 와 사실상 같은 자리라 그대로 옮긴다 */
function tm5186(ll) {
  const a = 6378137, f = 1 / 298.257222101, e2 = f * (2 - f), ep2 = e2 / (1 - e2);
  const lat0 = D.crs.lat0 * Math.PI / 180, lon0 = D.crs.lon0 * Math.PI / 180,
        FE = D.crs.fe, FN = D.crs.fn, K0 = D.crs.k0;
  const lat = ll.lat * Math.PI / 180, lon = ll.lng * Math.PI / 180;
  const m = p => a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * p
    - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * Math.sin(2 * p)
    + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * Math.sin(4 * p)
    - (35 * e2 ** 3 / 3072) * Math.sin(6 * p));
  const s = Math.sin(lat), c = Math.cos(lat), t = Math.tan(lat);
  const N = a / Math.sqrt(1 - e2 * s * s), T = t * t, C = ep2 * c * c, A = (lon - lon0) * c;
  return {
    E: FE + K0 * N * (A + (1 - T + C) * A ** 3 / 6
        + (5 - 18 * T + T * T + 72 * C - 58 * ep2) * A ** 5 / 120),
    N: FN + K0 * (m(lat) - m(lat0) + N * t * (A * A / 2 + (5 - T + 9 * C + 4 * C * C) * A ** 4 / 24
        + (61 - 58 * T + T * T + 600 * C - 330 * ep2) * A ** 6 / 720))
  };
}

/* 현황 건물: 수치지형도에서 뽑은 윤곽선(자료/현황건물.json).
   촬영 당시 서 있던 건물·구조물이다. 계획이 아니라 현황이다.
   ⚠ 도형 수천 개를 각각 만들면 느리다. 선 하나(L.polyline)에 조각을 다 담는다 */
const bldg = L.polyline((D['건물'] || []).map(l => l.map(p => [p[1], p[0]])),
  { color: '#00e5ff', weight: 1.1, opacity: .95, interactive: false });
let bldgOn = false;
function setBldg(on) {
  bldgOn = on;
  document.getElementById('bBldg').classList.toggle('on', on);
  if (on) bldg.addTo(map); else if (map.hasLayer(bldg)) map.removeLayer(bldg);
}

/* 현황 도로·구거: 같은 수치지형도에서 뽑는다(지형지물 부호 A=교통, E=수계) */
const road = L.polyline((D['도로'] || []).map(l => l.map(p => [p[1], p[0]])),
  { color: '#ff9f1c', weight: 1.1, opacity: .9, interactive: false });
const water = L.polyline((D['구거'] || []).map(l => l.map(p => [p[1], p[0]])),
  { color: '#4dabff', weight: 1.3, opacity: .9, interactive: false });
let rwOn = false;
function setRw(on) {
  rwOn = on;
  document.getElementById('bRw').classList.toggle('on', on);
  if (on) { road.addTo(map); water.addTo(map); }
  else { [road, water].forEach(l => { if (map.hasLayer(l)) map.removeLayer(l); }); }
}

/* 지적: 지적도의 **현황 필지**다. 계획 획지가 아니라 등록된 땅의 경계다.
   ⚠ 소유구분·편입은 토지조서에서 오는데, 조서와 지적도는 **기준일이 다를 수 있다.**
     필지 모양·지번·지목·도면 넓이(도면)와 소유·편입(조서)을 화면에서도 갈라 적는다
   ⚠ 수천 개를 SVG 로 그리면 버벅인다. 캔버스로 그리고, 켤 때 비로소 만든다 */
const CADD = D['지적'] || {};
const CAD = CADD['필지'] || [], CADB = CADD['기준'] || {};
const JM = { 답: '논', 전: '밭', 대: '대지', 도: '도로', 구: '구거', 천: '하천', 임: '임야',
  제: '제방', 장: '공장용지', 잡: '잡종지', 창: '창고용지', 목: '목장용지', 과: '과수원',
  유: '유지', 주: '주차장', 차: '주차장', 묘: '묘지', 종: '종교용지', 학: '학교용지', 체: '체육용지' };
const OWN = { 국: ['국유지', '#ffd166'], 공: ['공유지', '#c77dff'], 사: ['사유지', '#e6ecf2'] };
const cadRend = L.canvas({ padding: .3 });
const cadLay = L.layerGroup(), cadLabels = L.layerGroup();
let cadOn = false, cadBuilt = false;

function buildCad() {
  if (cadBuilt) return;
  cadBuilt = true;
  // 채움은 **국·공유지만** 진하게 한다. 사유지까지 채우면 블록 색과 겹쳐 화면이 탁해지고,
  // 정작 눈으로 찾아야 할 국공유지(무상귀속 협의 대상)가 묻힌다
  //
  // ⚠ 다만 도면 넓이와 조서 넓이가 크게 어긋난 필지(f['?']===2)는 **채우지 않고 점선으로** 그린다.
  //   조서가 이 필지 것이 아닐 수 있는데 진하게 칠하면 국공유지 넓이를 눈으로 셀 때
  //   크게 부풀려 보인다. 점선은 ｢믿지 말라｣는 표다
  const FILL = { 국: .22, 공: .22, 사: .03 };
  for (const f of CAD) {
    const c = OWN[f.o] ? OWN[f.o][1] : '#8e9aa6';
    const 의심 = f['?'] === 2;
    const poly = L.polygon(f.p.map(p => [p[1], p[0]]), { renderer: cadRend,
      color: c, weight: f.o ? 1.1 : .8, opacity: 의심 ? .6 : (f.o ? .95 : .5),
      dashArray: 의심 ? '5,4' : null,
      fillOpacity: 의심 ? 0 : (FILL[f.o] !== undefined ? FILL[f.o] : .02),
      fillColor: c });
    poly.on('click', ev => {
      if (measOn) mAdd(ev.latlng); else showLot(f, ev.latlng);
      L.DomEvent.stopPropagation(ev);
    });
    cadLay.addLayer(poly);
  }
}
function setCad(on) {
  cadOn = on;
  document.getElementById('bCad').classList.toggle('on', on);
  if (on) { buildCad(); cadLay.addTo(map); syncCad(); }
  else {
    [cadLay, cadLabels].forEach(l => { if (map.hasLayer(l)) map.removeLayer(l); });
    cadLabels.clearLayers();
  }
}
/* 지번을 다 붙이면 글자로 덮인다. 당겼을 때(z17 이상) 화면 안엣것만, 겹치면 건너뛴다 */
function syncCad() {
  if (!cadOn) return;
  cadLabels.clearLayers();
  if (map.getZoom() < 17) { if (map.hasLayer(cadLabels)) map.removeLayer(cadLabels); return; }
  const b = map.getBounds().pad(.05), put = [];
  let n = 0;
  for (const f of CAD) {
    if (n >= 260) break;
    if (!f.c || !b.contains([f.c[1], f.c[0]])) continue;
    const q = map.latLngToContainerPoint([f.c[1], f.c[0]]);
    if (put.some(o => Math.abs(o.x - q.x) < 40 && Math.abs(o.y - q.y) < 13)) continue;
    put.push(q); n++;
    cadLabels.addLayer(L.marker([f.c[1], f.c[0]], { interactive: false,
      icon: L.divIcon({ className: 'cad-label', iconSize: [40, 12], iconAnchor: [20, 6],
        html: f.j + (f.m ? ' <span style="opacity:.7">' + f.m + '</span>' : '') }) }));
  }
  if (!map.hasLayer(cadLabels)) cadLabels.addTo(map);
}
map.on('moveend zoomend', syncCad);

/* 필지 하나를 눌렀을 때: **도면에서 온 것과 조서에서 온 것을 갈라 적는다.**
   기준일이 다르기 때문이다. 위쪽은 믿어도 되고 아래쪽은 옛 기준이다 */
function showLot(f, ll) {
  const h = ll ? (gelev(ll) !== null ? gelev(ll) : elev(ll)) : null;
  let s = '<h3>' + (f.j || '지번 없는 필지')
    + (f.m ? ' <span style="color:var(--sub);font-weight:400">' + f.m
             + (JM[f.m] ? '(' + JM[f.m] + ')' : '') + '</span>' : '')
    + '</h3><div class="kv">' + (f['리'] ? f['리'] + ' · ' : '')
    + '도면 넓이 <b>' + fmt(f.s) + '㎡</b>';
  if (h !== null) s += ' · 누른 자리 지반고 <b>' + h.toFixed(1) + 'm</b>';
  if (f.o) {
    s += '<br><span class="old">' + (OWN[f.o] ? OWN[f.o][0] : f.o) + ' · ' + f.e + '편입'
       + (f.ea ? ' ' + fmt(f.ea) + '㎡' : '') + (f.ta ? ' · 조서 넓이 ' + fmt(f.ta) + '㎡' : '')
       + '<br>' + (CADB['조서'] || '토지조서') + '</span>';
    if (f['?'] === 2)
      s += '<br><span class="warn">⚠ 도면 넓이가 조서와 크게 다릅니다. 한 지번이 여러 조각으로'
         + ' 나뉜 것이거나, 조서가 이 필지 것이 아닐 수 있습니다</span>';
    else if (f['?'] === 1)
      s += '<br><span class="warn">⚠ 도면 넓이가 조서와 다소 다릅니다</span>';
    if (CADB['주의']) s += '<br><span class="warn">⚠ ' + CADB['주의'] + '</span>';
  } else if (f.j) {
    s += '<br><span class="old">조서에 없는 필지입니다'
       + '(구역 밖이거나 고시 뒤 갈린 필지)</span>';
  }
  card(s + '</div>');
  if (ll) mark(ll);
}

/* 지형: 등고선(자료/등고선.json). 주곡선 1m · 5m 마다 굵은 선.
   ⚠ DWG 를 GDAL 로 읽을 때 등고선이 몇 줄만 나오면 자료가 없는 게 아니라 못 읽은 것일 수 있다
     (블록으로 묶인 도형). DXF 로 바꿔 읽으면 풀린다 */
const CONT = D['등고선'] || [];
const toLL = c => c.p.map(p => [p[1], p[0]]);
const contMinor = L.polyline(CONT.filter(c => Math.round(c.h * 10) % 50 !== 0).map(toLL),
  { color: '#d7f08a', weight: .7, opacity: .65, interactive: false });
const contMajor = L.polyline(CONT.filter(c => Math.round(c.h * 10) % 50 === 0).map(toLL),
  { color: '#a8dc45', weight: 1.5, opacity: .95, interactive: false });
const CLAB = D['등고선표'] || [];
const contLabels = L.layerGroup();
let terrOn = false;
function setTerr(on) {
  terrOn = on;
  document.getElementById('bTerr').classList.toggle('on', on);
  if (on) { contMinor.addTo(map); contMajor.addTo(map); syncCont(); }
  else {
    [contMinor, contMajor, contLabels].forEach(l => { if (map.hasLayer(l)) map.removeLayer(l); });
    contLabels.clearLayers();
  }
}
/* 등고선 표고는 선을 따라 일정 간격마다 미리 잡아 둔 자리에 붙인다.
   다 붙이면 느리므로 화면 안에 든 것만, 그것도 당겼을 때만 붙인다.
   글자는 선 방향으로 눕힌다(각도는 만들 때 계산해 두었다) */
function syncCont() {
  if (!terrOn) return;
  contLabels.clearLayers();
  if (map.getZoom() < 17) { if (map.hasLayer(contLabels)) map.removeLayer(contLabels); return; }
  const b = map.getBounds().pad(0.05);
  const put = [];                       // 이미 붙인 자리(화면 좌표). 겹치면 건너뛴다
  let n = 0;
  // 5m 굵은 선을 먼저 붙인다. 가파른 데서는 자리가 모자라 뒤엣것이 밀리기 때문이다
  for (const pass of [1, 0]) {
    for (const c of CLAB) {
      if (n >= 300) break;
      const major = Math.round(c.h * 10) % 50 === 0;
      if ((pass === 1) !== major) continue;
      if (!b.contains([c.p[1], c.p[0]])) continue;
      const q = map.latLngToContainerPoint([c.p[1], c.p[0]]);
      if (put.some(o => Math.abs(o.x - q.x) < 34 && Math.abs(o.y - q.y) < 15)) continue;
      put.push(q); n++;
      contLabels.addLayer(L.marker([c.p[1], c.p[0]], { interactive: false,
        icon: L.divIcon({ className: 'cont-label', iconSize: [28, 12], iconAnchor: [14, 6],
          html: '<span style="display:inline-block;transform:rotate(' + c.a + 'deg)'
              + (major ? ';color:#f2ffd9;font-size:11px' : '') + '">' + c.h.toFixed(0) + '</span>' }) }));
    }
  }
  if (!map.hasLayer(contLabels)) contLabels.addTo(map);
}
map.on('moveend zoomend', syncCont);

const site = L.geoJSON({ type: 'FeatureCollection', features: D['구역계'] },
  { style: { color: '#ff3b30', weight: 2.5, fill: false }, interactive: false });
const blk = L.geoJSON(D['블록'], {
  style: f => ({ color: '#ffffff', weight: 1.2, opacity: .85,
                 fillColor: f.properties['색상'], fillOpacity: .12 }),
  onEachFeature: (f, l) => l.on('click', ev => {
    if (measOn) mAdd(ev.latlng); else show(f.properties, ev.latlng);
    L.DomEvent.stopPropagation(ev);
  })
});
const labels = L.layerGroup(D['블록'].features.map(f =>
  L.marker(L.geoJSON(f).getBounds().getCenter(), { interactive: false,
    icon: L.divIcon({ className: 'blk-label', html: f.properties['가구'], iconSize: [36, 14] }) })));

let lineOn = true;
function setLine(on) {
  lineOn = on;
  document.getElementById('bLine').classList.toggle('on', on);
  if (on) { site.addTo(map); blk.addTo(map); syncLabels(); }
  else { map.removeLayer(site); map.removeLayer(blk); map.removeLayer(labels); }
}
function syncLabels() {
  if (!lineOn) return;
  const want = map.getZoom() >= 15.5;
  if (want === map.hasLayer(labels)) return;
  if (want) labels.addTo(map); else map.removeLayer(labels);
}
map.on('zoomend zoom', syncLabels);

const fmt = n => (n || 0).toLocaleString('ko-KR');
function card(html) { document.getElementById('cardIn').innerHTML = html;
  document.getElementById('card').style.display = 'block'; }
function hide() {
  document.getElementById('card').style.display = 'none';
  if (pin && !measOn) { map.removeLayer(pin); pin = null; }
}
document.getElementById('cardX').onclick = e => { hide(); e.stopPropagation(); };
map.on('click', e => { if (measOn) mAdd(e.latlng); else showPoint(e.latlng); });
function show(p, ll) {
  const h = ll ? (gelev(ll) !== null ? gelev(ll) : elev(ll)) : null;
  card('<h3>블록 ' + p['가구'] + '</h3><div class="kv">' + p['용도'] + ' · '
    + fmt(p['면적_㎡']) + '㎡ · 획지 ' + p['획지수'] + '개'
    + (h === null ? '' : '<br>누른 자리 지반고 <b>' + h.toFixed(1) + 'm</b>') + '</div>');
  if (ll) mark(ll);
}

/* 누른 자리: 표고와 도면 좌표를 보여 준다 */
let pin = null;
function mark(ll) {
  if (pin) pin.setLatLng(ll);
  else pin = L.circleMarker(ll, { radius: 5, color: '#ffd60a', weight: 2,
    fillColor: '#ffd60a', fillOpacity: .5, interactive: false }).addTo(map);
}
function showPoint(ll) {
  const s = elev(ll), g = gelev(ll), t = tm5186(ll);
  let top;
  if (g === null && s === null) top = '표고 자료 밖입니다';
  else if (g === null) top = '표면 <b>' + s.toFixed(1) + 'm</b>';
  else {
    top = '지반 <b>' + g.toFixed(1) + 'm</b>';
    if (s !== null) {
      top += ' · 표면 ' + s.toFixed(1) + 'm';
      if (s - g >= 0.5) top += '<br>위에 선 것 높이 ' + (s - g).toFixed(1) + 'm';
    }
  }
  card('<h3>이 자리</h3><div class="kv">' + top
    + '<br>위경도 ' + ll.lat.toFixed(6) + ', ' + ll.lng.toFixed(6)
    + '<br>평면좌표(EPSG:' + D.crs.epsg + ') X ' + fmt(Math.round(t.N)) + ' · Y ' + fmt(Math.round(t.E))
    + '</div>');
  mark(ll);
}

/* 거리·면적 재기: 지도를 눌러 점을 찍는다 */
let measOn = false;
const mPts = [], mLay = L.layerGroup();
function setMeas(on) {
  measOn = on;
  document.getElementById('bMeas').classList.toggle('on', on);
  map.getContainer().style.cursor = on ? 'crosshair' : '';
  if (on) { mLay.addTo(map); mDraw(); }
  else { mPts.length = 0; mLay.clearLayers(); map.removeLayer(mLay); hide(); }
}
function mAdd(ll) { mPts.push(ll); mDraw(); }
window.mUndo = () => { mPts.pop(); mDraw(); };
window.mClear = () => { mPts.length = 0; mDraw(); };
function mDraw() {
  mLay.clearLayers();
  if (mPts.length >= 3) L.polygon(mPts, { color: '#ffd60a', weight: 0,
    fillColor: '#ffd60a', fillOpacity: .12, interactive: false }).addTo(mLay);
  if (mPts.length >= 2) L.polyline(mPts, { color: '#ffd60a', weight: 2,
    dashArray: '6,4', interactive: false }).addTo(mLay);
  mPts.forEach(p => L.circleMarker(p, { radius: 4, color: '#000', weight: 1,
    fillColor: '#ffd60a', fillOpacity: 1, interactive: false }).addTo(mLay));
  mCard();
}
/* 거리·면적은 평면직각좌표(기본 EPSG:5186)에서 잰다.
   도면·조서와 같은 기준이라 값이 그대로 맞는다. 구면 근사로 재면 0.1% 남짓 크게 나온다
   (원 사업에서 블록 하나를 재 보니 구면 +0.126%, 평면 -0.059%) */
function ringArea(pts) {          // ㎡
  const q = pts.map(tm5186);
  let s = 0;
  for (let i = 0, n = q.length; i < n; i++) {
    const a = q[i], b = q[(i + 1) % n];
    s += a.E * b.N - b.E * a.N;
  }
  return Math.abs(s / 2);
}
function segLen(p1, p2) {         // m
  const a = tm5186(p1), b = tm5186(p2);
  return Math.hypot(a.E - b.E, a.N - b.N);
}
function mCard() {
  if (!measOn) return;
  let d = 0;
  for (let i = 1; i < mPts.length; i++) d += segLen(mPts[i - 1], mPts[i]);
  const hh = mPts.map(p => gelev(p)).filter(v => v !== null);
  let s = '<h3>측정</h3><div class="kv">';
  if (!mPts.length) s += '지도를 눌러 점을 찍으십시오';
  else {
    s += '점 ' + mPts.length + '개 · 거리 <b>'
      + (d >= 1000 ? (d / 1000).toFixed(2) + 'km' : d.toFixed(1) + 'm') + '</b>';
    if (mPts.length >= 3) {
      const A = ringArea(mPts);
      s += '<br>면적 <b>' + fmt(Math.round(A)) + '㎡</b> · ' + (A / 10000).toFixed(2) + 'ha';
    }
    if (hh.length >= 2) s += '<br>지반고 ' + Math.min(...hh).toFixed(1) + '~'
      + Math.max(...hh).toFixed(1) + 'm · 고저차 '
      + (Math.max(...hh) - Math.min(...hh)).toFixed(1) + 'm';
  }
  s += '</div><div class="btns"><button onclick="mUndo()">되돌리기</button>'
    + '<button onclick="mClear()">지우기</button></div>';
  card(s);
}

function fit() { map.fitBounds(site.getBounds(), { padding: [30, 30] }); }
document.getElementById('bFit').onclick = fit;
document.getElementById('bLine').onclick = () => setLine(!lineOn);
document.getElementById('bHs').onclick = () => setHs((hsLv + 1) % 4);
document.getElementById('bMeas').onclick = () => setMeas(!measOn);
document.getElementById('bBldg').onclick = () => setBldg(!bldgOn);
document.getElementById('bRw').onclick = () => setRw(!rwOn);
document.getElementById('bCad').onclick = () => setCad(!cadOn);
document.getElementById('bTerr').onclick = () => setTerr(!terrOn);

if (window.innerWidth >= 900) L.control.zoom({ position: 'topright' }).addTo(map);
setLine(true);
fit();
</script></body></html>
"""


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    cfg = config.load()
    DATA, OUT, WORK = cfg["data_dir"], cfg["output_dir"], cfg["work_dir"]
    TILES = os.path.join(OUT, "tiles")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    # ⚠ 폴더를 통째로 지우지 않는다. 실자료면 안에 타일이 수만~수십만 장 들어 있다
    os.makedirs(OUT, exist_ok=True)
    if not os.path.isdir(TILES):
        sys.exit(f"타일이 없습니다: {TILES}\n  tiles_nogdal.py 또는 make_tiles.sh 로 먼저 만들어 주십시오")

    base = os.path.join(DATA, "base.json")
    if not os.path.exists(base):
        sys.exit(f"바탕 자료가 없습니다: {base}")
    data = load_json(base)
    data["zoom"] = cfg["ortho_zoom"]
    data["hsZoom"] = cfg["hs_zoom"]
    data["crs"] = cfg["crs"]

    for key, fname in [("dem", "dem.json"), ("지반", "지반고.json")]:
        p = os.path.join(WORK, fname)
        if os.path.exists(p):
            data[key] = load_json(p)
            print(f"  {fname} {data[key]['w']}×{data[key]['h']} · {data[key]['res']:.2f}m(메르카토르)")
        else:
            print(f"⚠ {fname} 이 없습니다. 표고 표시 일부가 빕니다")

    for key, fname, field in [("건물", "현황건물.json", "선"), ("도로", "도로.json", "선"),
                              ("구거", "구거.json", "선"),
                              ("지적", "지적.json", None),
                              ("등고선", "등고선.json", "선"), ("등고선표", "등고선.json", "표")]:
        p = os.path.join(DATA, fname)
        if os.path.exists(p):
            # 지적은 필지와 기준(기준일·주의 문구)을 함께 실어야 해서 통째로 넣는다(field 가 None)
            d = load_json(p)
            data[key] = d if field is None else d[field]
            n = len(data[key]["필지"]) if field is None else len(data[key])
            print(f"  {key} {n}개")
        else:
            print(f"  ({fname} 없음. 그 단추는 비어 보입니다)")
    if not os.path.isdir(os.path.join(OUT, "hs")):
        print("⚠ 음영기복 타일(hs) 이 없습니다. 음영 단추가 비어 보입니다")

    lab = cfg["labels"]
    html = TEMPLATE
    for tok, val in [
        ("/*__LEAFLET_CSS__*/", open(os.path.join(ROOT, "lib", "leaflet.css"), encoding="utf-8").read()),
        ("/*__LEAFLET_JS__*/", open(os.path.join(ROOT, "lib", "leaflet.js"), encoding="utf-8").read()),
        ("/*__DATA__*/", json.dumps(data, ensure_ascii=False)),
    ]:
        html = html.replace(tok, val, 1)
    for tok, val in [("/*__TITLE__*/", cfg["title"]), ("/*__SUBTITLE__*/", cfg["subtitle"]),
                     ("/*__FOOTER__*/", cfg["footer"]), ("/*__BUILD__*/", stamp),
                     ("/*__SURFACE_NOTE__*/", lab.get("surface_note", "")),
                     ("/*__GROUND_NOTE__*/", lab.get("ground_note", "")),
                     ("/*__CAD_NOTE__*/", lab.get("cadastral_note", ""))]:
        html = html.replace(tok, val)
    with open(os.path.join(OUT, "평면지도.html"), "w", encoding="utf-8") as f:
        f.write(html)
    # 윈도우 대비 탐침 파일(맥이 USB 에 쓰면 한글 이름이 NFD 로 바뀌는 문제를 화면이 알아채게 한다)
    with open(os.path.join(OUT, "한글확인.js"), "w", encoding="utf-8") as f:
        f.write("window.__KO=1;\n")
    print(f"평면지도.html {len(html)/1024:.0f}KB")

    n = sum(len(f) for _, _, f in os.walk(OUT))
    mb = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs) / 1048576
    print(f"\n{OUT}  파일 {n}개 · {mb:.1f}MB")


if __name__ == "__main__":
    main()
