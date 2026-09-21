#!/usr/bin/env python3
"""
사업부지 안내 지도 빌더 (휴대폰 우선, 단일 HTML)

설정 파일(config.json, 없으면 config.example.json)이 가리키는 GeoJSON·JSON과
Leaflet을 한 파일로 묶어 HTML 하나를 만든다. 파일을 더블클릭하면 그대로 열리고,
그대로 https 정적 호스팅에 올려도 동작한다.

왜 한 파일인가
    file:// 로 연 페이지에서는 fetch 로 옆 파일(JSON)을 읽지 못한다.
    그래서 자료와 라이브러리를 모두 HTML 안에 넣는다(인라인).
    배경지도만 인터넷 타일(기본 OpenStreetMap)이나 로컬 타일 폴더를 참조한다.

화면
    지도가 화면을 채우고 정보는 하단 시트(엿보기·절반·전체 세 단계)에 담는다.
    너비 900px 이상에서는 우측 패널로 바뀐다.
    내 위치: watchPosition 으로 계속 따라가며 사업구역 안팎·용도·블록을 알려 준다.
    바라보는 방향: 기기 나침반(없으면 걷는 방향)으로 부채꼴을 돌린다.
    구역 밖: 경계까지 거리와 길찾기 링크. 너무 멀면 지도를 옮기지 않는다.

사용
    python3 tools/build_site.py                       # output/guide-map.html
    python3 tools/build_site.py --config my.json --out output/my.html
    python3 tools/build_site.py --check               # 면적·위치 검산만

시험
    만든 HTML 주소 끝에 ?sim=위도,경도,방위 를 붙이면 ｢내 위치｣가 그 자리로 흉내 난다.
    예) guide-map.html?sim=36.6225,127.9040,45

주의
    ㎡(U+33A1)는 JS 식별자로 쓸 수 없다. 속성 접근은 반드시 대괄호로 한다.
"""
import argparse
import datetime
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
LIB = os.path.join(ROOT, "lib")


# ── 설정 ────────────────────────────────────────────────────────────────
def load_config(path=None):
    """config.json 이 있으면 그것을, 없으면 config.example.json 을 읽는다.
    API 키는 설정 파일보다 환경변수를 먼저 본다(저장소에 키가 들어가지 않게)."""
    if path is None:
        path = os.path.join(ROOT, "config.json")
        if not os.path.exists(path):
            path = os.path.join(ROOT, "config.example.json")
    cfg = json.load(open(path, encoding="utf-8"))
    cfg["_base"] = os.path.dirname(os.path.abspath(path))
    bm = cfg.setdefault("basemap", {})
    bm["vworld_key"] = os.environ.get("VWORLD_KEY", bm.get("vworld_key", "")) or ""
    return cfg


def strip_notes(o):
    """밑줄(_)로 시작하는 설명 항목을 떼어 낸다. 화면에 안 나와도 페이지 소스에는 실리기 때문"""
    if isinstance(o, dict):
        return {k: strip_notes(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [strip_notes(v) for v in o]
    return o


# 자료 파일에 섞여 있을 수 있는 내부용·개인정보 항목. 빌드 때 떼고 넣는다
DROP_KEYS = {"내부메모", "작업메모", "검토필요", "확인필요", "표기_제한",
             "소유자", "소유자주소", "소유구분", "보상등급", "보상난이도", "실거래가"}


def scrub(o):
    if isinstance(o, dict):
        return {k: scrub(v) for k, v in o.items() if k not in DROP_KEYS}
    if isinstance(o, list):
        return [scrub(v) for v in o]
    return o


def load_data(cfg):
    base = cfg["_base"]
    d = cfg["data"]

    def rd(key, required=True):
        p = d.get(key)
        if not p:
            if required:
                sys.exit(f"설정 data.{key} 가 비어 있다")
            return None
        full = p if os.path.isabs(p) else os.path.join(base, p)
        if not os.path.exists(full):
            if required:
                sys.exit(f"자료 파일이 없다: {p}  (tools/make_sample_data.py 로 예시를 만들 수 있다)")
            return None
        return scrub(json.load(open(full, encoding="utf-8")))

    return {"landuse": rd("landuse"), "blocks": rd("blocks"),
            "plan": rd("plan", False), "spots": rd("spots", False)}


# ── 검산 ────────────────────────────────────────────────────────────────
def _rings(geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return polys


def geom_area_m2(geom):
    """경위도 폴리곤 넓이(㎡). 좁은 지역이라 평면 근사로 충분하다(구멍은 뺀다)"""
    total = 0.0
    for poly in _rings(geom):
        lat0 = sum(p[1] for p in poly[0]) / len(poly[0])
        mlat, mlng = 111132.95, 111320.0 * math.cos(math.radians(lat0))
        for i, ring in enumerate(poly):
            s = 0.0
            for a, b in zip(ring, ring[1:]):
                s += (a[0] * mlng) * (b[1] * mlat) - (b[0] * mlng) * (a[1] * mlat)
            total += abs(s) / 2 * (1 if i == 0 else -1)
    return total


def in_ring(pt, ring):
    c = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > pt[1]) != (yj > pt[1])) and pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def in_geom(pt, geom):
    for poly in _rings(geom):
        if in_ring(pt, poly[0]) and not any(in_ring(pt, h) for h in poly[1:]):
            return True
    return False


def check(cfg, data):
    """면적 검산과 위치 검산을 따로 한다.
    면적은 도형이 상하·좌우로 뒤집혀도 그대로라 면적만 맞다고 위치까지 맞는 것은 아니다.
    그래서 블록 꼭짓점이 구역계 안에 드는지(위치)를 별도로 센다."""
    f = cfg["data"]["fields"]
    tol = cfg["data"].get("area_tolerance_pct", 0.5)
    bval = cfg["data"].get("boundary_value", "구역계")
    worst, problems = 0.0, []
    print(f"{'구분':<14}{'속성 ㎡':>12}{'도형 ㎡':>12}{'차이 %':>9}")
    for name, fc, key in (("토지이용", data["landuse"], f["use"]),
                          ("블록", data["blocks"], f["block"])):
        for ft in fc["features"]:
            p = ft["properties"]
            want = p.get(f["area"])
            got = geom_area_m2(ft["geometry"])
            if not want:
                continue
            dpc = (got - want) / want * 100
            worst = max(worst, abs(dpc))
            flag = "  <-- 확인" if abs(dpc) > tol else ""
            print(f"{name + ' ' + str(p.get(key)):<14}{want:>12,.0f}{got:>12,.0f}{dpc:>+9.2f}{flag}")
            if flag:
                problems.append(f"{name} {p.get(key)} 면적 차이 {dpc:+.2f}%")

    bnd = [x for x in data["landuse"]["features"] if x["properties"].get(f["use"]) == bval]
    if not bnd:
        sys.exit(f"토지이용 자료에 {f['use']}={bval} 인 구역계 도형이 없다")
    bgeom = bnd[0]["geometry"]
    pts = [pt for ft in data["blocks"]["features"]
           for poly in _rings(ft["geometry"]) for pt in poly[0][:-1]]
    inside = sum(1 for pt in pts if in_geom(pt, bgeom))
    rate = inside / len(pts) * 100 if pts else 0
    print(f"\n면적 최대 편차 {worst:.2f}% (허용 {tol}%)")
    print(f"위치 검산: 블록 꼭짓점 {len(pts)}개 중 구역계 안 {inside}개 ({rate:.1f}%)")
    if rate < 90:
        problems.append("블록이 구역계 밖으로 벗어남. 도형 상하 반전·좌표계 혼동부터 확인")
    return problems


# ── 템플릿 ──────────────────────────────────────────────────────────────
TEMPLATE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="theme-color" content="/*__THEME__*/">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
/*__HEAD_EXTRA__*/<title>/*__TITLE__*/</title>
<style>/*__LEAFLET_CSS__*/</style>
<style>
:root{
  --ink:#16181a; --sub:#697077; --line:#e0e3e7; --bg:#fff; --soft:#f4f6f8;
  --accent:/*__THEME__*/; --warn:#c0392b; --fs:15px; --sheet:18vh;
  --safe-b:env(safe-area-inset-bottom,0px); --safe-t:env(safe-area-inset-top,0px);
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;height:100%;overflow:hidden;overscroll-behavior:none;
  font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  color:var(--ink);font-size:var(--fs);line-height:1.55;-webkit-text-size-adjust:100%;background:#fff}
#map{position:absolute;inset:0;background:#e9eaec}
button{font-family:inherit;font-size:1em;color:inherit}
.notice{position:absolute;top:calc(8px + var(--safe-t));left:10px;right:10px;z-index:900;
  background:rgba(255,255,255,.96);border-left:3px solid var(--warn);border-radius:4px;
  padding:8px 10px;font-size:.82em;line-height:1.45;box-shadow:0 1px 6px rgba(0,0,0,.16);cursor:pointer}
.notice b{color:var(--warn)}
.notice .more{color:var(--sub);text-decoration:underline}
.fabs{position:absolute;left:10px;z-index:880;display:flex;flex-direction:column;gap:8px;
  top:calc(62px + var(--safe-t))}
.fab{min-width:46px;height:46px;padding:0 14px;border:1px solid var(--line);background:#fff;
  border-radius:23px;box-shadow:0 1px 5px rgba(0,0,0,.18);font-size:.85em;cursor:pointer;
  display:flex;align-items:center;justify-content:center;white-space:nowrap}
.fab.on{background:#1565c0;color:#fff;border-color:#1565c0}
.leaflet-top.leaflet-left{top:calc(62px + var(--safe-t));left:auto;right:0}
.card{position:absolute;left:10px;right:10px;z-index:895;background:#fff;border:1px solid var(--line);
  border-radius:10px;padding:12px 14px;display:none;box-shadow:0 3px 16px rgba(0,0,0,.22);
  bottom:calc(var(--sheet) + 14px);transition:bottom .22s;max-height:46vh;overflow-y:auto}
.card h3{margin:0 0 4px;font-size:1.05em;padding-right:24px}
.card .kv{color:var(--sub);font-size:.85em;margin-bottom:6px;font-variant-numeric:tabular-nums}
.card p{margin:0;font-size:.9em}
.card .x{position:absolute;top:2px;right:4px;padding:8px 10px;cursor:pointer;color:var(--sub);
  background:none;border:0;font-size:1.25em;line-height:1}
.card .go{display:inline-block;margin-top:10px;padding:10px 14px;border-radius:7px;
  background:var(--accent);color:#fff;text-decoration:none;font-size:.86em}
.big{font-size:1.5em;font-weight:700;color:var(--accent)}
.sheet{position:absolute;left:0;right:0;bottom:0;height:var(--sheet);z-index:1000;background:var(--bg);
  border-top:1px solid var(--line);border-radius:15px 15px 0 0;display:flex;flex-direction:column;
  box-shadow:0 -3px 18px rgba(0,0,0,.16);transition:height .22s;padding-bottom:var(--safe-b)}
.grip{padding:9px 0 5px;text-align:center;cursor:grab;touch-action:none;flex:none}
.grip:before{content:"";display:inline-block;width:40px;height:4px;border-radius:2px;background:#c8ccd0}
.head{padding:0 14px 9px;flex:none;display:flex;align-items:baseline;gap:8px}
.head h1{margin:0;font-size:1.0em}
.head p{margin:0;color:var(--sub);font-size:.78em;flex:1;text-align:right}
.tabs{display:flex;border-top:1px solid var(--line);border-bottom:1px solid var(--line);
  background:var(--soft);flex:none;overflow-x:auto;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tabs button{flex:1 0 auto;min-width:70px;padding:12px 10px;border:0;background:none;cursor:pointer;
  font-size:.85em;color:var(--sub);border-bottom:2px solid transparent;min-height:46px;white-space:nowrap}
.tabs button.on{color:var(--ink);font-weight:600;border-bottom-color:var(--accent);background:#fff}
.body{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;min-height:0}
.sec{padding:12px 14px;border-bottom:1px solid var(--line)}
.sec:last-child{border-bottom:0}
.sec>label{display:block;font-weight:600;font-size:.86em;color:#41474d;margin-bottom:8px}
.sec p{margin:0 0 8px;font-size:.92em}
.note{color:var(--sub);font-size:.82em;line-height:1.5}
.note.legal{color:#8a9099;font-size:.78em}
.me .dot{position:absolute;left:-9px;top:-9px;width:18px;height:18px;border-radius:50%;
  background:#1565c0;border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.45)}
.me .cone{position:absolute;left:-30px;top:-56px;width:60px;height:60px;
  filter:drop-shadow(0 1px 2px rgba(0,0,0,.35));
  transform-origin:50% 93.3%;transition:transform .12s linear;pointer-events:none}
input[type=range]{width:100%;accent-color:var(--accent);height:34px}
.chip{padding:10px 15px;border:1px solid var(--line);background:#fff;border-radius:19px;cursor:pointer;
  font-size:.85em;min-height:42px}
.chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.row{display:flex;gap:8px;flex-wrap:wrap}
.item{display:flex;align-items:center;gap:10px;padding:11px 0;cursor:pointer;user-select:none;
  border-top:1px solid var(--line);min-height:48px}
.item:first-of-type{border-top:0}
.item i{width:18px;height:14px;border:1px solid #9aa0a6;flex:none;border-radius:2px}
.item .t{flex:1;min-width:0}
.item .t b{display:block;font-weight:600;font-size:.94em}
.item .t small{color:var(--sub);font-size:.82em;display:block}
.item .n{color:var(--sub);font-variant-numeric:tabular-nums;font-size:.86em;text-align:right;flex:none}
.item.off{opacity:.34}
.tag{display:inline-block;background:#eceff1;color:#5b6167;border-radius:3px;padding:1px 6px;
  font-size:.78em;margin-left:5px;font-weight:400}
.blk-label{font-size:11px;font-weight:700;color:#fff;text-shadow:0 0 3px #000,0 0 3px #000;
  white-space:nowrap;pointer-events:none;text-align:center}
.spot-pin{background:#ffd400;border:2px solid #1a1a1a;border-radius:50%;width:28px;height:28px;
  display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;
  box-shadow:0 1px 4px rgba(0,0,0,.4)}
@media (min-width:900px){
  :root{--sheet:100%}
  .sheet{left:auto;right:0;top:0;width:364px;height:100%;border-radius:0;border-top:0;
    border-left:1px solid var(--line)}
  .grip{display:none}
  .head{padding-top:14px}
  .notice{right:382px;max-width:520px}
  .card{right:auto;bottom:16px;max-width:420px;left:10px}
  .leaflet-top.leaflet-left{right:376px}
}
</style></head><body>
<div id="map"></div>
<div class="notice" id="notice"><span id="noticeShort"></span> <span class="more">자세히</span>
  <span id="noticeMore" hidden></span></div>
<div class="fabs">
  <button class="fab" id="bLoc">내 위치</button>
  <button class="fab" id="bFit">전체</button>
  <button class="fab" id="bBg">배경</button>
</div>
<div class="card" id="card"><button class="x" id="cardX" aria-label="닫기">×</button><div id="cardIn"></div></div>
<div class="sheet" id="sheet">
  <div class="grip" id="grip"></div>
  <div class="head"><h1 id="ttl"></h1><p id="sub"></p></div>
  <div class="tabs" id="tabs"></div>
  <div class="body" id="body"></div>
</div>
<script>/*__LEAFLET_JS__*/</script>
<script>
const CFG = /*__CFG__*/;
const GJ = /*__LANDUSE__*/;
const BLK = /*__BLOCKS__*/;
const PLAN = /*__PLAN__*/;
const SPOTS = /*__SPOTS__*/;
const WEB = /*__WEB__*/;
const BUILD = '/*__BUILD__*/';
const F = CFG.data.fields;
const ORDER = CFG.data.use_order || [];
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt = n => Math.round(n).toLocaleString('ko-KR');
const el = (t, c, h) => { const d = document.createElement(t); if (c) d.className = c;
  if (h !== undefined) d.innerHTML = h; return d; };
const wide = () => window.innerWidth >= 900;
const link = (tpl, lat, lng, name) => tpl.replace('{lat}', lat.toFixed(6)).replace('{lng}', lng.toFixed(6))
  .replace('{name}', encodeURIComponent(name || ''));

document.getElementById('ttl').textContent = CFG.site.heading;
document.getElementById('noticeShort').innerHTML = CFG.notice.short;
document.getElementById('noticeMore').innerHTML = '<br>' + CFG.notice.more;

/* ── 지도 ─────────────────────────────────────────────── */
const map = L.map('map', {
  minZoom: 6, maxZoom: 21,
  zoomSnap: 0, zoomDelta: 1,
  scrollWheelZoom: false,      // 아래 smoothWheel 에서 직접 처리
  inertia: true, inertiaDeceleration: 2400,
  zoomControl: window.innerWidth >= 900, attributionControl: true });

/* 휠·트랙패드 확대를 손끝에 붙여 따라가게 한다.
   Leaflet 기본 휠 확대는 입력을 잠시 모았다가 한 번에 옮기는 방식이라
   트랙패드처럼 잘게 이어지는 입력에서 툭툭 끊긴다. 기본 처리를 끄고 직접 구현한다. */
(function smoothWheel() {
  const box = map.getContainer();
  let target = null, anchor = null, raf = null, fallback = null;
  box.addEventListener('wheel', e => {
    e.preventDefault();
    const px = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;   // 1 = 줄 단위, 0 = 픽셀 단위
    const step = -px / 200;           // 감도. 휠 한 칸(약 100)이 반 단계. 이 숫자 하나만 고치면 된다
    const base = target === null ? map.getZoom() : target;
    target = Math.max(map.getMinZoom(), Math.min(map.getMaxZoom(), base + step));
    anchor = map.mouseEventToContainerPoint(e);
    if (!raf) {
      raf = requestAnimationFrame(tick);
      fallback = setTimeout(flush, 200);   // 탭이 숨어 화면 갱신이 멈춘 경우 대비
    }
  }, { passive: false });
  function tick() {
    if (fallback) { clearTimeout(fallback); fallback = null; }
    const cur = map.getZoom(), gap = target - cur;
    if (Math.abs(gap) < 0.004) { raf = null; target = null; return; }
    // 남은 거리의 30%씩 좁혀 나간다. 시작은 빠르고 끝은 부드럽다. 커서 자리를 기준으로 확대
    map.setZoomAround(map.containerPointToLatLng(anchor), cur + gap * 0.3, { animate: false });
    raf = requestAnimationFrame(tick);
  }
  function flush() {
    fallback = null;
    if (raf) { cancelAnimationFrame(raf); raf = null; }
    if (target !== null && anchor)
      map.setZoomAround(map.containerPointToLatLng(anchor), target, { animate: false });
    target = null;
  }
})();

/* 배경지도. 설정(basemap.choice)에 따라 고른다. 저작권 표기는 반드시 붙인다 */
const BM = CFG.basemap;
const BG = [];
if (BM.choice === 'osm') {
  BG.push(['지도', L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxNativeZoom: 19, maxZoom: 21,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' })]);
} else if (BM.choice === 'vworld' && BM.vworld_key) {
  const vw = (layer, ext) => L.tileLayer('https://api.vworld.kr/req/wmts/1.0.0/' + BM.vworld_key
    + '/' + layer + '/{z}/{y}/{x}.' + ext, { maxNativeZoom: 19, maxZoom: 21, attribution: '배경 브이월드' });
  BG.push(['위성', vw('Satellite', 'jpeg')], ['지도', vw('Base', 'png')]);
} else if (BM.choice === 'custom' && BM.custom_url) {
  BG.push(['지도', L.tileLayer(BM.custom_url, { maxZoom: 21, attribution: BM.custom_attribution || '' })]);
} else if (BM.choice === 'local') {
  // 배포 폴더의 tiles/{z}/{x}/{y}.확장자. 서비스워커가 캐시 우선으로 담아 두어 통신이 끊겨도 뜬다
  BG.push(['지도', L.tileLayer('tiles/{z}/{x}/{y}.' + (BM.local_ext || 'jpeg'),
    { minNativeZoom: BM.local_minzoom, maxNativeZoom: BM.local_maxzoom, maxZoom: 21,
      attribution: BM.custom_attribution || '' })]);
}
BG.push(['없음', null]);
let bgIdx = 0, bgLayer = null;
function setBg(i) {
  if (bgLayer) map.removeLayer(bgLayer);
  bgIdx = i; bgLayer = BG[i][1];
  if (bgLayer) bgLayer.addTo(map);
  document.getElementById('bBg').textContent = '배경: ' + BG[i][0];
  document.querySelectorAll('[data-bg]').forEach(b => b.classList.toggle('on', +b.dataset.bg === i));
}
document.getElementById('bBg').onclick = () => setBg((bgIdx + 1) % BG.length);

/* 토지이용 */
const BVAL = CFG.data.boundary_value;
const boundary = GJ.features.find(f => f.properties[F.use] === BVAL);
const uses = GJ.features.filter(f => f.properties[F.use] !== BVAL)
  .sort((a, b) => ORDER.indexOf(a.properties[F.use]) - ORDER.indexOf(b.properties[F.use]));
const TOTAL = boundary.properties[F.area] || 0;
const pct = a => TOTAL ? (a / TOTAL * 100).toFixed(1) : '-';
let fillOp = 0.55;
const layers = {}, hidden = new Set();
uses.forEach(f => {
  const p = f.properties;
  const lyr = L.geoJSON(f, { style: { color: '#00000055', weight: 0.6,
    fillColor: p[F.color] || '#999', fillOpacity: fillOp } });
  lyr.on('click', ev => { showUse(p[F.use], ev.latlng); L.DomEvent.stopPropagation(ev); });
  layers[p[F.use]] = lyr.addTo(map);
});
const bLyr = L.geoJSON(boundary, { style: { color: '#d32f2f', weight: 2.4, fill: false },
  interactive: false }).addTo(map);
const SITE_C = bLyr.getBounds().getCenter();

/* 블록. 채움 없이 선만 그려 용도 색을 가리지 않는다(누를 수 있게 아주 옅은 채움은 남김) */
const BSTYLE = { color: '#141414', weight: 1.6, opacity: 0.9, fill: true, fillColor: '#000', fillOpacity: 0.02 };
const HSTYLE = { color: '#1565c0', weight: 4, opacity: 1, fill: true, fillColor: '#1565c0', fillOpacity: 0.12 };
const blkLayer = L.geoJSON(BLK, {
  style: () => BSTYLE,
  onEachFeature: (f, l) => l.on('click', ev => { showBlock(f.properties); L.DomEvent.stopPropagation(ev); })
}).addTo(map);
const blkLabels = L.layerGroup();
BLK.features.forEach(f => {
  blkLabels.addLayer(L.marker(L.geoJSON(f).getBounds().getCenter(), { interactive: false,
    icon: L.divIcon({ className: 'blk-label', html: esc(f.properties[F.block]), iconSize: [36, 14] }) }));
});
// 많이 물러서면 이름이 겹쳐 글자 덩어리가 되므로 이름만 감춘다
function syncBlkLabels() {
  const want = map.getZoom() >= 14.5;
  if (want !== map.hasLayer(blkLabels)) { if (want) blkLabels.addTo(map); else map.removeLayer(blkLabels); }
}
map.on('zoomend', syncBlkLabels);
let hiBlock = null;
function highlightBlock(name) {
  if (hiBlock === name) return;
  hiBlock = name;
  blkLayer.eachLayer(l => l.setStyle(l.feature.properties[F.block] === name ? HSTYLE : BSTYLE));
}

/* 로드뷰 지점 */
const spotLayer = L.layerGroup();
let spotOn = false;
if (SPOTS) SPOTS['지점'].forEach(s => {
  L.marker([s.lat, s.lng], { icon: L.divIcon({ className: '', iconSize: [28, 28],
    html: '<div class="spot-pin">' + esc(s['번호']) + '</div>' }) })
    .on('click', () => showSpot(s)).addTo(spotLayer);
});
function setSpot(on) { spotOn = on; if (on) spotLayer.addTo(map); else map.removeLayer(spotLayer); }

/* ── 시트 ─────────────────────────────────────────────── */
const SNAPS = [0.18, 0.46, 0.88];   // 접어도 손잡이·제목·탭은 보여야 한다
let snap = 0;
function applySheet() {
  document.documentElement.style.setProperty('--sheet', wide() ? '100%' : Math.round(SNAPS[snap] * 100) + 'vh');
}
function peek() { if (!wide()) { snap = 0; applySheet(); setTimeout(() => map.invalidateSize(), 240); } }

/* 지도에서 실제로 보이는 부분을 그때그때 잰다(시트·고지창이 지도를 덮는다) */
function obscured() {
  const c = map.getContainer().getBoundingClientRect();
  const sh = document.getElementById('sheet').getBoundingClientRect();
  const nt = document.getElementById('notice').getBoundingClientRect();
  let right = Math.max(0, c.right - sh.left), bottom = Math.max(0, c.bottom - sh.top);
  if (bottom > c.height * 0.9) bottom = 0;
  if (right > c.width * 0.9) right = 0;
  return { top: Math.min(c.height * 0.4, Math.max(16, nt.bottom - c.top + 10)),
           right: Math.min(c.width * 0.6, right + 16), bottom: Math.min(c.height * 0.6, bottom + 16) };
}
function fitSite(fly) {
  const o = obscured();
  const pad = { paddingTopLeft: [16, Math.round(o.top)], paddingBottomRight: [Math.round(o.right), Math.round(o.bottom)] };
  // 첫 배치를 애니메이션으로 하면 전환이 끝나지 않은 채 남아 이후 확대·축소가 먹히지 않는다
  if (fly) map.flyToBounds(bLyr.getBounds(), Object.assign({ duration: 0.9 }, pad));
  else map.fitBounds(bLyr.getBounds(), Object.assign({ animate: false }, pad));
}

/* ── 카드 ─────────────────────────────────────────────── */
const PLANBY = {};
if (PLAN) PLAN['용지'].forEach(r => PLANBY[r['구분']] = r);
let cardIsMine = false;
function card(html) {
  cardIsMine = false;
  document.getElementById('cardIn').innerHTML = html;
  document.getElementById('card').style.display = 'block';
}
function hideCard() { document.getElementById('card').style.display = 'none'; }
document.getElementById('cardX').onclick = ev => { hideCard(); ev.stopPropagation(); };
map.on('click', hideCard);
function rvLink(lat, lng, label) {
  if (!CFG.links.roadview) return '';
  return '<a class="go" href="' + link(CFG.links.roadview, lat, lng) + '" target="_blank" rel="noopener">'
    + esc(label || CFG.links.roadview_label) + '</a> ';
}
function useDesc(use) { const r = PLANBY[use]; return r && r['설명'] ? '<p>' + esc(r['설명']) + '</p>' : ''; }
function showUse(use, latlng) {
  const f = uses.find(x => x.properties[F.use] === use), a = f ? f.properties[F.area] : 0;
  let h = '<h3>' + esc(use) + '</h3><div class="kv">' + fmt(a) + ' ㎡ · ' + pct(a) + '%</div>' + useDesc(use);
  if (latlng) {
    const b = blockAt(latlng.lat, latlng.lng);
    if (b) h += '<p class="note" style="margin-top:6px">이 자리는 블록 ' + esc(b.properties[F.block]) + ' 입니다.</p>';
    h += rvLink(latlng.lat, latlng.lng, '이 지점 로드뷰 보기');
  }
  card(h);
}
function showBlock(p) {
  let h = '<h3>블록 ' + esc(p[F.block]) + '<span class="tag">' + esc(p[F.use]) + '</span></h3>'
    + '<div class="kv">' + fmt(p[F.area]) + ' ㎡' + (p[F.lots] ? ' · 획지 ' + p[F.lots] + '개' : '') + '</div>'
    + useDesc(p[F.use]);
  card(h);
}
function showSpot(s) {
  card('<h3>' + esc(s['번호']) + '. ' + esc(s['명']) + '</h3>'
    + '<div class="kv">단지는 이 지점에서 ' + esc(s['단지방위_도']) + '° 방향</div>'
    + '<p>' + esc(s['설명']) + '</p>' + rvLink(s.lat, s.lng));
}
function showText(t, body) { card('<h3>' + t + '</h3><p>' + body + '</p>'); }

/* ── 위치 판정 ─────────────────────────────────────────── */
function inRing(pt, ring) {
  let c = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
    if (((yi > pt[1]) !== (yj > pt[1])) && (pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi)) c = !c;
  }
  return c;
}
function inGeom(pt, g) {
  const polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates;
  for (const pl of polys) {
    if (!inRing(pt, pl[0])) continue;
    let hole = false;
    for (let i = 1; i < pl.length; i++) if (inRing(pt, pl[i])) { hole = true; break; }
    if (!hole) return true;
  }
  return false;
}
function useAt(lat, lng) { for (const f of uses) if (inGeom([lng, lat], f.geometry)) return f.properties[F.use]; return null; }
function blockAt(lat, lng) { for (const f of BLK.features) if (inGeom([lng, lat], f.geometry)) return f; return null; }
/* 구역계 경계까지 가장 가까운 거리(m). 좁은 지역이라 평면 근사 */
function distToBoundary(lat, lng) {
  const ml = 111132.95, mg = 111320 * Math.cos(lat * Math.PI / 180);
  const g = boundary.geometry, polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates;
  let best = Infinity;
  polys.forEach(pl => pl.forEach(ring => {
    for (let i = 0; i + 1 < ring.length; i++) {
      const ax = (ring[i][0] - lng) * mg, ay = (ring[i][1] - lat) * ml;
      const bx = (ring[i + 1][0] - lng) * mg, by = (ring[i + 1][1] - lat) * ml;
      const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
      const t = L2 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / L2)) : 0;
      best = Math.min(best, Math.hypot(ax + t * dx, ay + t * dy));
    }
  }));
  return best;
}
const km = m => m >= 1000 ? (m / 1000).toFixed(m >= 10000 ? 0 : 1) + 'km' : Math.round(m) + 'm';

/* 내 위치 표시. 점 하나로는 어느 쪽을 보는지 알 수 없어 나침반에 맞춰 도는 부채꼴을 얹는다 */
const ME_HTML =
  '<svg class="cone" viewBox="0 0 60 60" width="60" height="60">'
  + '<defs><radialGradient id="mecg" cx="50%" cy="93%" r="80%">'
  + '<stop offset="0%" stop-color="#1e88e5" stop-opacity=".95"/>'
  + '<stop offset="55%" stop-color="#1e88e5" stop-opacity=".72"/>'
  + '<stop offset="100%" stop-color="#1e88e5" stop-opacity=".40"/></radialGradient></defs>'
  + '<path d="M30 56 L7 13 A30 30 0 0 1 53 13 Z" fill="none" stroke="#fff" stroke-opacity=".9" stroke-width="2.5" stroke-linejoin="round"/>'
  + '<path d="M30 56 L7 13 A30 30 0 0 1 53 13 Z" fill="url(#mecg)"/></svg><b class="dot"></b>';
const NEWS = ['북', '북동', '동', '남동', '남', '남서', '서', '북서'];
const compassName = deg => NEWS[Math.round(deg / 45) % 8];
let heading = null, headFrom = null;

function applyHeading() {
  const cone = locMarker && locMarker.getElement() && locMarker.getElement().querySelector('.cone');
  if (!cone) return;
  if (heading === null) { cone.style.display = 'none'; return; }
  cone.style.display = '';
  cone.style.transform = 'rotate(' + heading.toFixed(1) + 'deg)';
}
function onOrient(e) {
  let h = null;
  if (typeof e.webkitCompassHeading === 'number' && !isNaN(e.webkitCompassHeading)) h = e.webkitCompassHeading; // 아이폰
  else if (e.absolute && typeof e.alpha === 'number' && e.alpha !== null) h = 360 - e.alpha;                  // 안드로이드
  if (h === null) return;
  const so = (screen.orientation && screen.orientation.angle) || window.orientation || 0;  // 가로 화면 보정
  heading = ((h + so) % 360 + 360) % 360; headFrom = '나침반';
  applyHeading();
}
function startCompass() {
  const D = window.DeviceOrientationEvent;
  if (!D) return;
  const bind = () => {
    window.addEventListener('deviceorientationabsolute', onOrient, true);
    window.addEventListener('deviceorientation', onOrient, true);
  };
  // 아이폰은 사용자가 누른 그 순간에만 권한을 물을 수 있다
  if (typeof D.requestPermission === 'function') D.requestPermission().then(r => { if (r === 'granted') bind(); }).catch(() => {});
  else bind();
}
function stopCompass() {
  window.removeEventListener('deviceorientationabsolute', onOrient, true);
  window.removeEventListener('deviceorientation', onOrient, true);
  heading = null; headFrom = null;
}

let locMarker = null, accCircle = null, watchId = null, follow = true, firstFix = true, lastPos = null;
const bLocEl = document.getElementById('bLoc');

function locCard(p) {
  const lat = p.coords.latitude, lng = p.coords.longitude, acc = p.coords.accuracy;
  const inside = inGeom([lng, lat], boundary.geometry);
  const u = useAt(lat, lng), b = blockAt(lat, lng);
  const hd = heading !== null ? '<br>바라보는 쪽 <b>' + compassName(heading) + '</b> ' + Math.round(heading) + '° (' + headFrom + ')' : '';
  let body;
  if (inside) {
    body = (b ? '<div class="big">블록 ' + esc(b.properties[F.block]) + '</div>' : '')
      + '<p>사업구역 <b>안</b>입니다. 계획 용도는 <b>' + esc(u || '판정 불가') + '</b>입니다.</p>'
      + (b ? useDesc(b.properties[F.use]) : '');
  } else {
    body = '<p>사업구역 <b>밖</b>입니다. 경계까지 약 <b>' + km(distToBoundary(lat, lng)) + '</b>.</p>'
      + (CFG.links.directions ? '<a class="go" href="' + link(CFG.links.directions, SITE_C.lat, SITE_C.lng, CFG.site.place_name)
         + '" target="_blank" rel="noopener">' + esc(CFG.links.directions_label) + '</a> ' : '');
  }
  card('<h3>내 위치 <span class="tag">추적 중</span></h3>'
    + '<div class="kv">' + lat.toFixed(6) + ', ' + lng.toFixed(6) + ' · 오차 약 ' + Math.round(acc) + 'm' + hd + '</div>'
    + body + (inside ? rvLink(lat, lng) : ''));
  cardIsMine = true;      // card() 가 false 로 되돌리므로 그 뒤에 세운다
}

function onPos(p) {
  lastPos = p;
  const lat = p.coords.latitude, lng = p.coords.longitude, acc = p.coords.accuracy;
  // 단지에서 너무 멀면 따라가지 않는다. 옮겨 봐야 단지와 무관한 곳이라 방향을 잃는다
  if (SITE_C.distanceTo([lat, lng]) > CFG.location.range_km * 1000) { outOfRange(lat, lng, acc); return; }
  if (!locMarker) {
    accCircle = L.circle([lat, lng], { radius: acc, color: '#1565c0', weight: 1,
      fillColor: '#1565c0', fillOpacity: .12, interactive: false }).addTo(map);
    locMarker = L.marker([lat, lng], { zIndexOffset: 1000,
      icon: L.divIcon({ className: 'me', html: ME_HTML, iconSize: [0, 0] }) }).addTo(map);
    locMarker.on('click', () => { if (lastPos) locCard(lastPos); });   // 닫은 카드를 다시 보려면 점을 누른다
  } else {
    locMarker.setLatLng([lat, lng]);
    accCircle.setLatLng([lat, lng]).setRadius(acc);
  }
  // 나침반이 없는 기기는 걷는 중(초속 0.7m 이상)에 한해 이동 방향을 쓴다
  if (headFrom !== '나침반' && typeof p.coords.heading === 'number' && !isNaN(p.coords.heading) && p.coords.speed > 0.7) {
    heading = p.coords.heading; headFrom = '이동 방향';
  }
  applyHeading();
  const b = blockAt(lat, lng);
  highlightBlock(b ? b.properties[F.block] : null);
  if (follow) map.setView([lat, lng], Math.max(map.getZoom(), CFG.location.follow_zoom), { animate: true });
  // 카드는 첫 위치에서만 연다. 이후엔 열려 있을 때만 갈아 끼운다(닫아도 되살아나지 않게)
  const open = document.getElementById('card').style.display === 'block';
  if (firstFix) { locCard(p); firstFix = false; }
  else if (open && cardIsMine) locCard(p);
}
function outOfRange(lat, lng, acc) {
  stopWatch();          // 배터리를 계속 쓰지 않도록 추적을 멈춘다
  const m = SITE_C.distanceTo([lat, lng]);
  card('<h3>단지에서 멀리 있습니다</h3>'
    + '<div class="kv">' + lat.toFixed(6) + ', ' + lng.toFixed(6) + ' · 오차 약 ' + Math.round(acc) + 'm</div>'
    + '<p>현재 위치가 단지에서 약 <b>' + km(m) + '</b> 떨어져 있어 지도를 옮기지 않았습니다. 단지 가까이 와서 다시 눌러 주십시오.</p>'
    + (CFG.links.directions ? '<a class="go" href="' + link(CFG.links.directions, SITE_C.lat, SITE_C.lng, CFG.site.place_name)
       + '" target="_blank" rel="noopener">' + esc(CFG.links.directions_label) + '</a>' : ''));
}
function onErr() {
  stopWatch();
  showText('내 위치', '위치를 가져오지 못했습니다. 브라우저 위치 권한과 기기 위치 설정을 확인해 주십시오.'
    + (location.protocol === 'http:' && location.hostname !== 'localhost' ? '<br>휴대폰에서는 <b>https 주소</b>라야 위치가 잡힙니다.' : ''));
}

/* 시험용 가짜 위치. 주소 끝 ?sim=위도,경도[,방위] */
const SIM = (() => {
  const m = location.search.match(/[?&]sim=([-\d.]+),([-\d.]+)(?:,([-\d.]+))?/);
  return m ? { lat: +m[1], lng: +m[2], hd: m[3] === undefined ? null : +m[3] } : null;
})();

function startWatch() {
  follow = true; firstFix = true;
  bLocEl.textContent = '추적 중지'; bLocEl.classList.add('on');
  peek();
  if (SIM) {
    watchId = -1;
    if (SIM.hd !== null) { heading = SIM.hd; headFrom = '시험값'; }
    onPos({ coords: { latitude: SIM.lat, longitude: SIM.lng, accuracy: 5, heading: null, speed: 0 } });
    return;
  }
  if (!navigator.geolocation) { stopWatch(); showText('내 위치', '이 브라우저는 위치 기능을 지원하지 않습니다.'); return; }
  showText('내 위치', '위치를 확인하고 있습니다.');
  startCompass();
  watchId = navigator.geolocation.watchPosition(onPos, onErr, { enableHighAccuracy: true, maximumAge: 2000, timeout: 15000 });
}
function stopWatch() {
  stopCompass();
  firstFix = true; lastPos = null;
  if (watchId !== null && watchId !== -1) navigator.geolocation.clearWatch(watchId);
  watchId = null;
  bLocEl.textContent = '내 위치'; bLocEl.classList.remove('on');
}
bLocEl.onclick = () => { if (watchId === null) startWatch(); else { stopWatch(); hideCard(); } };
map.on('dragstart', () => { follow = false; });   // 사용자가 지도를 끌면 따라가기를 멈춘다
document.getElementById('bFit').onclick = () => { hideCard(); fitSite(true); };

/* 시트 손잡이 끌기 */
const grip = document.getElementById('grip');
let dragY = null, dragStart = 0, moved = false;
grip.addEventListener('pointerdown', e => {
  if (wide()) return;
  dragY = e.clientY; dragStart = SNAPS[snap]; moved = false; grip.setPointerCapture(e.pointerId);
});
grip.addEventListener('pointermove', e => {
  if (dragY === null) return;
  if (Math.abs(e.clientY - dragY) > 4) moved = true;
  const r = Math.min(0.92, Math.max(0.10, dragStart + (dragY - e.clientY) / window.innerHeight));
  document.documentElement.style.setProperty('--sheet', Math.round(r * 100) + 'vh');
});
grip.addEventListener('pointerup', e => {
  if (dragY === null) return;
  if (!moved) snap = (snap + 1) % SNAPS.length;
  else {
    const r = dragStart + (dragY - e.clientY) / window.innerHeight;
    let best = 0, bd = 9;
    SNAPS.forEach((v, i) => { const d = Math.abs(v - r); if (d < bd) { bd = d; best = i; } });
    snap = best;
  }
  dragY = null; applySheet(); setTimeout(() => map.invalidateSize(), 240);
});
document.getElementById('sheet').addEventListener('transitionend', e => { if (e.propertyName === 'height') map.invalidateSize(); });

/* ── 탭 ────────────────────────────────────────────────── */
const bodyEl = document.getElementById('body');
const RENDER = { plan: renderPlan, blk: renderBlk, rv: renderRv, info: renderInfo };
const TABS = CFG.tabs.filter(t => RENDER[t.id] && (t.id !== 'rv' || SPOTS));
const tabsEl = document.getElementById('tabs');
TABS.forEach((t, i) => {
  const b = el('button', i === 0 ? 'on' : '', esc(t.label));
  b.dataset.t = t.id;
  b.onclick = () => {
    tabsEl.querySelectorAll('button').forEach(x => x.classList.remove('on'));
    b.classList.add('on');
    if (!wide() && snap === 0) { snap = 1; applySheet(); setTimeout(() => map.invalidateSize(), 240); }
    render(t.id);
  };
  tabsEl.appendChild(b);
});
function render(tab) {
  bodyEl.innerHTML = '';
  RENDER[tab]();
  if (tab !== 'rv' && spotOn) setSpot(false);
  // 고지 배너를 접어 두고 지나칠 수 있어 탭마다 아래에 한 줄 더 남긴다
  bodyEl.appendChild(el('div', 'sec note legal', CFG.notice.legal));
  bodyEl.scrollTop = 0;
}
function renderPlan() {
  const s1 = el('div', 'sec');
  s1.appendChild(el('label', '', '배경'));
  const row = el('div', 'row');
  BG.forEach((b, i) => { const c = el('button', 'chip' + (i === bgIdx ? ' on' : ''), b[0]);
    c.dataset.bg = i; c.onclick = () => setBg(i); row.appendChild(c); });
  s1.appendChild(row); bodyEl.appendChild(s1);

  const s2 = el('div', 'sec');
  s2.appendChild(el('label', '', '계획도 진하기 <span id="opv">' + Math.round(fillOp * 100) + '%</span>'));
  const r = el('input'); r.type = 'range'; r.min = 0; r.max = 100; r.value = Math.round(fillOp * 100);
  r.oninput = () => { fillOp = r.value / 100; document.getElementById('opv').textContent = r.value + '%';
    Object.values(layers).forEach(l => l.setStyle({ fillOpacity: fillOp })); };
  s2.appendChild(r); bodyEl.appendChild(s2);

  const s3 = el('div', 'sec');
  s3.appendChild(el('label', '', '용도별 면적 <span class="note">(눌러서 켜고 끄기)</span>'));
  uses.forEach(f => {
    const p = f.properties, use = p[F.use];
    const it = el('div', 'item' + (hidden.has(use) ? ' off' : ''));
    const sw = el('i'); sw.style.background = p[F.color] || '#999'; it.appendChild(sw);
    it.appendChild(el('div', 't', '<b>' + esc(use) + '</b>'));
    it.appendChild(el('div', 'n', fmt(p[F.area]) + '㎡<br><small>' + pct(p[F.area]) + '%</small>'));
    it.onclick = () => { const off = it.classList.toggle('off');
      if (off) { map.removeLayer(layers[use]); hidden.add(use); } else { layers[use].addTo(map); hidden.delete(use); } };
    s3.appendChild(it);
  });
  bodyEl.appendChild(s3);
  // 같은 화면을 여러 곳에 올릴 수 있으므로 판 표시를 남긴다. 갈무리만 봐도 어느 판인지 가린다
  bodyEl.appendChild(el('div', 'sec note', '사업면적 ' + fmt(TOTAL) + ' ㎡'
    + (PLAN && PLAN['메타'] && PLAN['메타']['기준'] ? ' · 기준 ' + esc(PLAN['메타']['기준']) : '')
    + '<br>화면 판 ' + BUILD + (WEB ? ' <span id="upd"></span>' : '')));
  if (WEB) checkUpdate();
}
function renderBlk() {
  const byUse = {};
  BLK.features.forEach(f => (byUse[f.properties[F.use]] = byUse[f.properties[F.use]] || []).push(f));
  Object.keys(byUse).sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b)).forEach(use => {
    const sec = el('div', 'sec');
    const sum = byUse[use].reduce((s, f) => s + (f.properties[F.area] || 0), 0);
    sec.appendChild(el('label', '', esc(use) + ' <span class="note">' + byUse[use].length + '개 블록 · ' + fmt(sum) + '㎡</span>'));
    byUse[use].forEach(f => {
      const p = f.properties, it = el('div', 'item');
      const sw = el('i'); sw.style.background = p[F.color] || '#999'; it.appendChild(sw);
      it.appendChild(el('div', 't', '<b>블록 ' + esc(p[F.block]) + '</b>' + (p[F.lots] ? '<small>획지 ' + p[F.lots] + '개</small>' : '')));
      it.appendChild(el('div', 'n', fmt(p[F.area]) + '㎡'));
      it.onclick = () => { map.flyToBounds(L.geoJSON(f).getBounds(), { padding: [40, 40], maxZoom: 17, duration: 0.9 });
        peek(); showBlock(p); };
      sec.appendChild(it);
    });
    bodyEl.appendChild(sec);
  });
}
function renderRv() {
  setSpot(true);
  const sec = el('div', 'sec');
  if (SPOTS['메타'] && SPOTS['메타']['용도']) sec.appendChild(el('p', 'note', esc(SPOTS['메타']['용도'])));
  SPOTS['지점'].forEach(s => {
    const it = el('div', 'item');
    it.appendChild(el('div', 't', '<b>' + esc(s['번호']) + '. ' + esc(s['명']) + '</b><small>' + esc(s['설명']) + '</small>'));
    it.onclick = () => { map.setView([s.lat, s.lng], 17); peek(); showSpot(s); };
    sec.appendChild(it);
  });
  bodyEl.appendChild(sec);
}
function renderInfo() {
  const s = el('div', 'sec', CFG.info_html || '');
  if (CFG.site.contact) s.appendChild(el('p', 'note', esc(CFG.site.contact)));
  bodyEl.appendChild(s);
}

/* ── 보조 ─────────────────────────────────────────────── */
document.getElementById('notice').onclick = () => { const m = document.getElementById('noticeMore'); m.hidden = !m.hidden; };
let rz;
window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { applySheet(); map.invalidateSize(); }, 180); });

if (WEB && 'serviceWorker' in navigator && location.protocol !== 'file:') {
  // 서비스워커는 https(또는 localhost)에서만 등록된다. file:// 에서는 오류가 난다
  navigator.serviceWorker.register('sw.js').catch(() => {});
}
async function checkUpdate() {
  // 서비스워커가 옛 화면을 붙들고 있으면 새 판이 안 보인다. 새 판이 있으면 한 번에 새로 받게 한다
  if (location.protocol === 'file:') return;
  try {
    const reg = 'serviceWorker' in navigator ? await navigator.serviceWorker.getRegistration() : null;
    if (reg) await reg.update();
    const html = await (await fetch('index.html', { cache: 'reload' })).text();
    const m = html.match(/const BUILD = '([^']+)'/);
    const u = document.getElementById('upd');
    if (m && m[1] !== BUILD && u) {
      u.innerHTML = '· <b style="color:var(--warn)">새 판 ' + esc(m[1]) + ' 있음</b> <a href="#" id="reloadNow" style="color:var(--accent)">새로 받기</a>';
      document.getElementById('reloadNow').onclick = async ev => {
        ev.preventDefault();
        if (reg) { try { await reg.unregister(); } catch (e) {} }
        if (window.caches) { const ks = await caches.keys(); await Promise.all(ks.filter(k => k.indexOf('shell') >= 0).map(k => caches.delete(k))); }
        location.reload();
      };
    }
  } catch (e) {}
}

document.getElementById('sub').textContent = '블록 ' + BLK.features.length + '개 · ' + fmt(TOTAL) + '㎡';
applySheet();
setBg(0);
fitSite();
syncBlkLabels();
// 글꼴과 시트 높이가 늦게 확정되는 경우가 있어 자리를 잡은 뒤 한 번 더 맞춘다
setTimeout(() => { map.invalidateSize(); fitSite(); }, 400);
render(TABS[0].id);
</script></body></html>
"""


def js(o):
    """<script> 안에 넣을 JSON. </script> 로 태그가 끊기지 않게 </ 를 풀어 쓴다"""
    return json.dumps(o, ensure_ascii=False).replace("</", "<\\/")


def stamp():
    """화면에 찍을 판 표시. 옛 판이 남아 있는지 눈으로 가릴 수 있게 한다"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def build(cfg, out_path, web=False, build_id=None):
    data = load_data(cfg)
    problems = check(cfg, data)
    for p in problems:
        print("경고:", p)
    pub = strip_notes({k: v for k, v in cfg.items() if not k.startswith("_")})
    pub.pop("deploy", None)
    bm = pub.get("basemap", {})
    if bm.get("choice") == "vworld" and not bm.get("vworld_key"):
        print("경고: basemap.choice=vworld 인데 키가 없다. 배경 없이 만든다 (환경변수 VWORLD_KEY)")
    if bm.get("choice") != "vworld":
        bm["vworld_key"] = ""        # 쓰지 않는 키는 HTML 에 싣지 않는다
    head = ""
    if web:
        head = ('<link rel="manifest" href="manifest.json">\n'
                # 이 줄이 없으면 브라우저가 /favicon.ico 를 찾아가 방문마다 404 가 남는다
                '<link rel="icon" href="icon-192.png" type="image/png">\n'
                '<link rel="apple-touch-icon" href="icon-192.png">\n')
    html = TEMPLATE.replace("/*__THEME__*/", cfg["site"].get("theme_color", "#2e6e64"))
    for mark, value in [
        ("/*__HEAD_EXTRA__*/", head),
        ("/*__TITLE__*/", cfg["site"]["title"]),
        ("/*__LEAFLET_CSS__*/", open(os.path.join(LIB, "leaflet.css"), encoding="utf-8").read()),
        ("/*__LEAFLET_JS__*/", open(os.path.join(LIB, "leaflet.js"), encoding="utf-8").read()),
        ("/*__CFG__*/", js(pub)),
        ("/*__LANDUSE__*/", js(data["landuse"])),
        ("/*__BLOCKS__*/", js(data["blocks"])),
        ("/*__PLAN__*/", js(data["plan"])),
        ("/*__SPOTS__*/", js(data["spots"])),
        ("/*__WEB__*/", "true" if web else "false"),
        ("/*__BUILD__*/", build_id or stamp()),
    ]:
        html = html.replace(mark, value, 1)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    open(out_path, "w", encoding="utf-8").write(html)
    print(f"저장 {os.path.relpath(out_path, ROOT)}  ({len(html) / 1024:.0f}KB, "
          f"블록 {len(data['blocks']['features'])}개)")
    return html


def main():
    ap = argparse.ArgumentParser(description="사업부지 안내 지도(단일 HTML) 빌더")
    ap.add_argument("--config", help="설정 파일 (기본: config.json, 없으면 config.example.json)")
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "guide-map.html"))
    ap.add_argument("--check", action="store_true", help="면적·위치 검산만 하고 끝낸다")
    a = ap.parse_args()
    cfg = load_config(a.config)
    if a.check:
        problems = check(cfg, load_data(cfg))
        sys.exit(1 if problems else 0)
    build(cfg, a.out, web=False)


if __name__ == "__main__":
    main()
