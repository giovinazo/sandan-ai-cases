#!/usr/bin/env python3
"""정사영상을 씌운 입체 지형(입체지도.html)을 만든다

  python3 scripts/build_3d.py --config sample_data/config.json

  ㅇ 바탕그림 = 이미 만든 정사영상 타일(설정 view_3d.tex_zoom 배율)을 이어 붙여 한 장으로
  ㅇ 높이 = 표면(dem.json) 과 지반(지반고.json) 두 벌. 화면에서 바꿔 볼 수 있다(지반이 없으면 표면을 두 번 쓴다)
  ㅇ 웹지엘(three.js)로 그린다. 인터넷 없이 더블클릭으로 돈다
  ㅇ 측정 도구·설명 탭은 measure_tool.py 가 만들어 `<!--__MEASURE__-->` 자리에 넣는다

⚠ 웹지엘은 file:// 로 읽은 그림을 CORS 로 막는다(origin 'null'). 캔버스로 우회해도 막힌다.
  그래서 바탕그림도 높이 자료도 **화면 파일 안에 data: 로 담는다**(data: 는 같은 출처로 쳐 준다).
  그림 한 변(max_side)을 키우면 또렷해지지만 파일이 커진다(원 사업: 6,144px · 15.6MB).
⚠ 화면 좌표는 웹메르카토르라 이 위도에서 실제보다 약 1.25배 크다. 길이·넓이는 평면직각좌표로
  되돌려 잰다(tm_to_scene 의 2차식. 1차식이면 4km 범위에서 45cm 어긋난다).

필요 패키지: numpy, Pillow  (GDAL 필요 없음)
"""
import base64
import datetime
import io
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import config  # noqa: E402
import measure_tool  # noqa: E402
from tmproj import TM, WORLD, lonlat_to_merc, tile_res  # noqa: E402

Image.MAX_IMAGE_PIXELS = 400_000_000


def merc_bounds(tm, box):
    E = np.linspace(box[0], box[2], 9)
    N = np.linspace(box[1], box[3], 9)
    EE, NN = np.meshgrid(E, N)
    lon, lat = tm.inverse(EE.ravel(), NN.ravel())
    x, y = lonlat_to_merc(lon, lat)
    return float(x.min()), float(y.min()), float(x.max()), float(y.max())


def stitch(tiles_dir, bounds, z, max_side, quality):
    """타일을 이어 붙여 한 장으로 -> (data URI, (w, h), 실제 범위, m/화소)"""
    x0, y0, x1, y1 = bounds
    n = 2**z
    tx0 = int((x0 + WORLD / 2) / WORLD * n)
    tx1 = int((x1 + WORLD / 2) / WORLD * n)
    ty0 = int((WORLD / 2 - y1) / WORLD * n)
    ty1 = int((WORLD / 2 - y0) / WORLD * n)
    mpp = tile_res(z)
    w, h = (tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256
    print(f"바탕그림 z{z} 타일 {tx1-tx0+1}×{ty1-ty0+1}장 → {w}×{h} 화소 ({mpp:.3f}m/화소)")
    canvas = Image.new("RGB", (w, h), (20, 20, 20))
    miss = 0
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            p = os.path.join(tiles_dir, str(z), str(tx), f"{ty}.jpg")
            if not os.path.exists(p):
                miss += 1
                continue
            canvas.paste(Image.open(p).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        canvas = canvas.resize((int(w * scale), int(h * scale)), Image.BOX)
        print(f"  그림 한 변 한계에 맞춰 {canvas.size[0]}×{canvas.size[1]} 로 줄임")
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=quality)
    print(f"  바탕그림 {buf.tell()/1048576:.1f}MB(파일 안에 담음) · 빠진 타일 {miss}장")
    mx0 = tx0 * 256 * mpp - WORLD / 2
    my1 = WORLD / 2 - ty0 * 256 * mpp
    uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return uri, (w, h), (mx0, my1 - h * mpp, mx0 + w * mpp, my1), mpp


def load_grid(path):
    d = json.load(open(path, encoding="utf-8"))
    raw = base64.b64decode(d["b64"])
    v = np.frombuffer(raw, dtype="<i2").reshape(d["h"], d["w"]).astype("float64")
    v[v == -32768] = np.nan
    return d, v / 10.0


def height(path, bounds, gw, gh, name):
    """표고 격자(json)를 입체 그물 격자(gw×gh)로 쌍선형 재표본 -> base64 Int16(데시미터)"""
    d, v = load_grid(path)
    x0, y0, x1, y1 = bounds
    xs = x0 + (np.arange(gw) + 0.5) * (x1 - x0) / gw
    ys = y1 - (np.arange(gh) + 0.5) * (y1 - y0) / gh
    X, Y = np.meshgrid(xs, ys)
    col = np.clip((X - d["x0"]) / d["res"], 0, d["w"] - 1.0001)
    row = np.clip((d["y0"] - Y) / d["res"], 0, d["h"] - 1.0001)
    c0, r0 = np.floor(col).astype(int), np.floor(row).astype(int)
    fx, fy = col - c0, row - r0
    a = (v[r0, c0] * (1 - fx) * (1 - fy) + v[r0, c0 + 1] * fx * (1 - fy)
         + v[r0 + 1, c0] * (1 - fx) * fy + v[r0 + 1, c0 + 1] * fx * fy)
    bad = ~np.isfinite(a)
    if bad.any():                              # 가장자리 빈 곳은 중앙값으로
        a[bad] = np.nanmedian(a)
    print(f"  {name} {gw}×{gh} · {a.min():.1f}~{a.max():.1f}m")
    q = np.clip(np.round(a * 10), -32000, 32000).astype("<i2")
    return base64.b64encode(q.tobytes()).decode(), float(a.min()), float(a.max())


def tm_to_scene(tm, box, bounds, wm, hm):
    """평면직각좌표(E,N) -> 화면 좌표 2차식 계수. 잔차를 찍어 둔다"""
    mx0, my0, mx1, my1 = bounds
    E0, N0, E1, N1 = box
    pad = 0.1 * max(E1 - E0, N1 - N0)            # 범위보다 조금 넓게 맞춘다(가장자리 어긋남 방지)
    E0, N0, E1, N1 = E0 - pad, N0 - pad, E1 + pad, N1 + pad
    rows = []
    for i in range(8):
        for j in range(8):
            E = E0 + (E1 - E0) * i / 7
            N = N0 + (N1 - N0) * j / 7
            lon, lat = tm.inverse(E, N)
            x, y = lonlat_to_merc(lon, lat)
            sx = (x - mx0) / (mx1 - mx0) * wm - wm / 2          # 동
            sz = -((y - my0) / (my1 - my0) * hm - hm / 2)       # 북이 화면 안쪽
            rows.append((E, N, float(sx), float(sz)))
    Ec, Nc = (E0 + E1) / 2, (N0 + N1) / 2
    def terms(E, N):
        e, n = E - Ec, N - Nc
        return [1, e, n, e * e, n * n, e * n]
    A = np.array([terms(r[0], r[1]) for r in rows])
    cx, *_ = np.linalg.lstsq(A, np.array([r[2] for r in rows]), rcond=None)
    cz, *_ = np.linalg.lstsq(A, np.array([r[3] for r in rows]), rcond=None)
    res = np.hypot(A @ cx - np.array([r[2] for r in rows]), A @ cz - np.array([r[3] for r in rows]))
    print(f"  평면좌표→화면 2차식 잔차 최대 {res.max()*1000:.2f}mm")
    return {"c": [Ec, Nc], "x": [float(v) for v in cx], "z": [float(v) for v in cz]}


def boundary(tm, base_path):
    """사업지구 경계(base.json 의 구역계, 위경도) -> 평면직각좌표 고리 목록"""
    if not os.path.exists(base_path):
        print("  ⚠ base.json 이 없어 사업경계는 건너뜁니다")
        return []
    d = json.load(open(base_path, encoding="utf-8"))
    rings = []
    def walk(c, depth):
        if depth == 1:
            if len(c) >= 3:
                E, N = tm.forward([p[0] for p in c], [p[1] for p in c])
                rings.append([[round(float(e), 2), round(float(n), 2)] for e, n in zip(E, N)])
        else:
            for x in c:
                walk(x, depth - 1)
    for f in d.get("구역계", []):
        g = f["geometry"]
        walk(g["coordinates"], 2 if g["type"] == "Polygon" else 3)
    print(f"  사업경계 {len(rings)}줄 · 꼭짓점 {sum(len(r) for r in rings):,}")
    return rings


def building_mask(path, bounds, w, h):
    """건물 윤곽을 격자에 찍어 비트로 눌러 담는다(한 칸 1비트). 테두리는 1.5m 부풀린다.
    화면에서 ｢여기는 건물｣ 을 가리는 데(분류 색·건물 측정 어림) 쓴다"""
    if not os.path.exists(path):
        print("  ⚠ 현황건물.json 이 없어 건물 표시는 건너뜁니다")
        return ""
    lines = json.load(open(path, encoding="utf-8"))["선"]
    x0, y0, x1, y1 = bounds
    cw = (x1 - x0) / w
    im = Image.new("1", (w, h), 0)
    dr = ImageDraw.Draw(im)
    lw = max(1, int(round(3.0 / cw)))
    for l in lines:
        X, Y = lonlat_to_merc([p[0] for p in l], [p[1] for p in l])
        pts = [((x - x0) / cw, (y1 - y) / cw) for x, y in zip(X, Y)]
        if len(pts) >= 3:
            dr.polygon(pts, fill=1, outline=1)
        dr.line(pts, fill=1, width=lw)
    m = np.asarray(im, dtype=bool)
    print(f"  건물로 표시한 칸 {int(m.sum()):,} ({100*m.mean():.1f}%)")
    return base64.b64encode(np.packbits(m.reshape(-1))).decode()


HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>/*__TITLE__*/(입체)</title>
<style>
html,body{margin:0;height:100%;background:#0e1013;color:#eef2f5;overflow:hidden;
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif}
canvas{display:block}
.bar{position:fixed;left:0;right:0;top:0;padding:10px 14px;pointer-events:none;
  background:linear-gradient(#0e1013dd,#0e101300)}
.bar b{font-size:15px} .bar span{color:#9aa4ad;font-size:12px;margin-left:8px}
button.jump{background:#1f5f52;border-color:#2f8d78;color:#d8fff5}
.panel{position:fixed;left:14px;bottom:14px;background:#1b1f24ee;border:1px solid #333a41;
  border-radius:12px;padding:12px 14px;min-width:230px}
.row{display:flex;align-items:center;gap:8px;margin:7px 0}
.row label{color:#9aa4ad;font-size:12px;width:52px}
input[type=range]{flex:1}
button{background:#272c32;color:#eef2f5;border:1px solid #3a424a;border-radius:8px;
  padding:6px 11px;font-size:12px;cursor:pointer}
button.on{background:#00d0a4;color:#08221c;border-color:#00d0a4}
.hint{color:#7e888f;font-size:11px;margin-top:8px;line-height:1.45}
.foot{position:fixed;right:12px;bottom:10px;color:#69737a;font-size:11px;text-align:right}
#keymap{position:fixed;right:12px;top:44px;background:#12151aee;border:1px solid #333a41;
  border-radius:10px}
</style></head><body>
<div class="bar"><b>/*__TITLE__*/</b><span>입체 · 표면/지반 · 지장물 높이 · 측정</span></div>
<div class="panel">
  <div class="row"><label>높이 과장</label><input type="range" id="ex" min="1" max="5" step="0.1" value="2">
    <span id="exv" style="width:26px;text-align:right">2×</span></div>
  <div class="row"><label>지형</label>
    <button id="bSurf" class="on">표면</button><button id="bGnd">지반</button></div>
  <div class="row"><label>색</label>
    <button id="cPhoto" class="on">사진</button><button id="cObj">지장물 높이</button>
    <button id="cCls">분류</button></div>
  <div class="row" id="legend" style="display:none;color:#9aa4ad;font-size:11px"></div>
  <div class="row"><label>보기</label>
    <button id="bTop">바로 위</button><button id="bTilt">비스듬히</button>
    <button id="bReset">처음</button></div>
  <div class="row"><label>표시</label>
    <button id="bBnd" class="on">사업경계</button><button id="bMap" class="on">키맵</button>
    <button id="bRe">새로고침</button>
    <button class="jump" onclick="location.href=koURL('./평면지도.html')">&lsaquo; 평면으로</button></div>
  <div class="row"><label>측정</label>
    <button id="msB">건물</button><button id="msH">높이</button>
    <button id="msA">면적</button><button id="msD">거리</button></div>
  <div class="row"><label></label>
    <button id="msL"><span id="msN">측정 0건</span></button>
    <button id="msHelpBtn">설명</button></div>
  <div class="hint"><b>끌기 = 옮기기</b>(지도와 같음) · 휠 = 커서 자리 확대<br>
    <b>오른쪽 끌기</b>(또는 Shift+끌기) = 돌리기·기울이기<br>
    /*__SURFACE_NOTE__*/ · /*__GROUND_NOTE__*/<br>
    <b>측정</b> = 건물을 누르면 면적·치수·높이 · 근거는 ｢설명｣</div>
</div>
<canvas id="keymap" width="200" height="216"></canvas>
<div class="foot">/*__FOOTER__*/ · 판 /*__BUILD__*/</div>
<script>
/* 윈도우 대비 탐침: 맥이 USB(exFAT)에 쓰면 한글 이름이 NFD 로 바뀐다. 윈도우는 바이트가
   같아야 찾으므로, 한글 이름 파일(한글확인.js)이 열리는 형태를 보고 링크 형태를 정한다 */
var KO_NFD=false;
(function(){var s=document.createElement('script');s.src='./\ud55c\uae00\ud655\uc778.js';
  s.onerror=function(){KO_NFD=true;};document.head.appendChild(s);})();
function koURL(p){return KO_NFD? p.normalize('NFD'):p;}
</script>
<script>/*__THREE__*/</script>
<script>
const D = /*__DATA__*/;
function unpack(b64){
  const s = atob(b64), buf = new ArrayBuffer(s.length), u8 = new Uint8Array(buf);
  for (let i=0;i<s.length;i++) u8[i]=s.charCodeAt(i);
  return new Int16Array(buf);
}
const HS = { 표면: unpack(D.surf), 지반: unpack(D.gnd) };
const W = D.w, H = D.h, MPP = D.mpp * D.step;      // 격자 한 칸이 실제 몇 m 인가
const wm = (W-1)*MPP, hm = (H-1)*MPP;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0e1013);
scene.fog = new THREE.Fog(0x0e1013, wm*1.2, wm*3.2);
const camera = new THREE.PerspectiveCamera(45, innerWidth/innerHeight, 1, wm*8);
const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);

scene.add(new THREE.AmbientLight(0xffffff, 0.75));
const sun = new THREE.DirectionalLight(0xfff2e0, 1.15);
sun.position.set(-wm*0.6, wm*0.9, -hm*0.5);
scene.add(sun);

const geo = new THREE.PlaneGeometry(wm, hm, W-1, H-1);
geo.rotateX(-Math.PI/2);
const tex = new THREE.TextureLoader().load(D.tex, () => render());
tex.colorSpace = THREE.SRGBColorSpace;
tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({map:tex, roughness:1, metalness:0}));
scene.add(mesh);

/* 건물 자리(도화 윤곽). 비트로 눌러 담은 것을 푼다 */
const BLD = (function(){
  if (!D.bld) return null;
  const s = atob(D.bld), u = new Uint8Array(s.length);
  for (let i=0;i<s.length;i++) u[i]=s.charCodeAt(i);
  return u;
})();
const isBld = i => BLD ? ((BLD[i>>3] >> (7-(i&7))) & 1) === 1 : false;

/* 색 세 가지. 사진은 그림을 씌우고, 나머지는 칸마다 색을 칠한다 */
let mode = 'photo';
const colAttr = new THREE.BufferAttribute(new Float32Array(W*H*3), 3);
geo.setAttribute('color', colAttr);
function setMode(m){
  mode = m;
  const lg = document.getElementById('legend');
  ['cPhoto','cObj','cCls'].forEach(id => document.getElementById(id).classList.toggle('on',
    (id==='cPhoto'&&m==='photo')||(id==='cObj'&&m==='obj')||(id==='cCls'&&m==='cls')));
  const mat = mesh.material;
  if (m === 'photo'){
    mat.map = tex; mat.vertexColors = false; mat.color.set(0xffffff);
    lg.style.display = 'none';
  } else {
    mat.map = null; mat.vertexColors = true; mat.color.set(0xffffff);
    const s = HS['표면'], g = HS['지반'], a = colAttr.array;
    for (let i=0;i<W*H;i++){
      const d = (s[i]-g[i])/10;                 // 위에 선 것의 높이(m)
      let r,gr,b;
      if (m === 'obj'){
        const t = Math.max(0, Math.min(1, d/6));
        if (d < 0.3){ r=0.62; gr=0.60; b=0.56; }         // 맨땅
        else { r = 0.35+0.65*t; gr = 0.72-0.55*t; b = 0.30-0.22*t; }
      } else {
        if (isBld(i)){ r=0.91; gr=0.54; b=0.35; }        // 건물
        else if (d > 1.5){ r=0.50; gr=0.75; b=0.42; }    // 나무·수풀
        else { r=0.78; gr=0.72; b=0.60; }                // 지면
      }
      a[i*3]=r; a[i*3+1]=gr; a[i*3+2]=b;
    }
    colAttr.needsUpdate = true;
    lg.style.display = 'flex';
    lg.innerHTML = (m === 'obj')
      ? '맨땅 회색 · 낮음 초록 → <b style="color:#e88a5a">높음 주황</b> (0~6m)'
      : '<b style="color:#e88a5a">건물</b> · <b style="color:#7fbf6a">나무·수풀(1.5m 초과)</b> · 지면';
    mat.needsUpdate = true;
  }
  mat.needsUpdate = true;
  render();
}

let ex = 2, which = '표면';
function apply(){
  const src = HS[which], pos = geo.attributes.position;
  const base = D.base;
  for (let i=0;i<src.length;i++) pos.setY(i, (src[i]/10 - base) * ex);
  pos.needsUpdate = true; geo.computeVertexNormals(); render();
}

/* 조작. 라이브러리를 더 받지 않으려고 직접 짰다.
   **왼쪽 끌기 = 옮기기**(지도처럼 지면을 잡아 끈다) · 오른쪽/Shift 끌기 = 돌리기·기울이기
   위아래 끌기는 아래로 끌면 눕는다(처음엔 반대로 되어 있어 고쳤다) */
const target = new THREE.Vector3(0,0,0);
let dist = wm*0.95, yaw = -0.6, pitch = 0.72;
function place(){
  camera.position.set(target.x + dist*Math.cos(pitch)*Math.sin(yaw),
                      target.y + dist*Math.sin(pitch),
                      target.z + dist*Math.cos(pitch)*Math.cos(yaw));
  camera.lookAt(target);
}
function render(){
  place();
  renderer.render(scene, camera);
  if (typeof KM !== 'undefined') KM.draw();
}

/* 커서가 가리키는 지면 자리. 이 자리를 붙잡고 끌면 손에 붙어 움직인다 */
const rayc = new THREE.Raycaster(), plane = new THREE.Plane(new THREE.Vector3(0,1,0), 0);
const hit = new THREE.Vector3();
function groundAt(cx, cy){
  rayc.setFromCamera(new THREE.Vector2(cx/innerWidth*2-1, -(cy/innerHeight)*2+1), camera);
  plane.constant = -target.y;
  return rayc.ray.intersectPlane(plane, hit) ? hit.clone() : null;
}

let drag = null;
renderer.domElement.addEventListener('mousedown', e => {
  const rot = (e.button === 2 || e.shiftKey);
  drag = {x:e.clientX, y:e.clientY, rot, grab: rot ? null : groundAt(e.clientX, e.clientY)};
  e.preventDefault();
});
addEventListener('mouseup', () => drag = null);
addEventListener('mousemove', e => {
  if (!drag) return;
  if (drag.rot){
    const dx = e.clientX-drag.x, dy = e.clientY-drag.y;
    drag.x = e.clientX; drag.y = e.clientY;
    yaw -= dx*0.005;
    pitch = Math.max(0.08, Math.min(1.5, pitch - dy*0.005));   // 아래로 끌면 눕는다
  } else {
    if (!drag.grab) return;
    const now = groundAt(e.clientX, e.clientY);
    if (!now) return;
    target.add(drag.grab.clone().sub(now));                     // 잡은 자리를 손끝에 붙인다
    const lim = Math.max(wm, hm);
    target.x = Math.max(-lim, Math.min(lim, target.x));
    target.z = Math.max(-lim, Math.min(lim, target.z));
  }
  render();
});
renderer.domElement.addEventListener('contextmenu', e => e.preventDefault());

/* 휠은 커서가 가리키는 자리를 붙잡고 확대한다 */
renderer.domElement.addEventListener('wheel', e => {
  e.preventDefault();
  const g = groundAt(e.clientX, e.clientY);
  const before = dist;
  dist = Math.max(wm*0.03, Math.min(wm*3, dist * Math.exp(e.deltaY*0.0012)));
  if (g){
    const f = dist/before;
    target.set(g.x + (target.x-g.x)*f, target.y, g.z + (target.z-g.z)*f);
  }
  render();
}, {passive:false});

/* 손가락으로도 - 한 손가락 옮기기, 두 손가락 확대 */
let touch = null;
renderer.domElement.addEventListener('touchstart', e => {
  if (e.touches.length === 1) touch = {grab: groundAt(e.touches[0].clientX, e.touches[0].clientY)};
  else if (e.touches.length === 2){
    const d = Math.hypot(e.touches[0].clientX-e.touches[1].clientX,
                         e.touches[0].clientY-e.touches[1].clientY);
    touch = {pinch: d, dist0: dist};
  }
  e.preventDefault();
}, {passive:false});
renderer.domElement.addEventListener('touchmove', e => {
  if (!touch) return;
  if (touch.grab && e.touches.length === 1){
    const now = groundAt(e.touches[0].clientX, e.touches[0].clientY);
    if (now) target.add(touch.grab.clone().sub(now));
  } else if (touch.pinch && e.touches.length === 2){
    const d = Math.hypot(e.touches[0].clientX-e.touches[1].clientX,
                         e.touches[0].clientY-e.touches[1].clientY);
    dist = Math.max(wm*0.03, Math.min(wm*3, touch.dist0 * touch.pinch / Math.max(d,1)));
  }
  render(); e.preventDefault();
}, {passive:false});
addEventListener('touchend', () => touch = null);

addEventListener('resize', () => {
  camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  render();
});

/* ── 평면좌표 -> 화면 좌표(2차식, build_3d.py 가 맞춘 계수) ───────── */
function toScene(E, N){
  const t = D.tm2s, e = E - t.c[0], n = N - t.c[1];
  const b = [1, e, n, e*e, n*n, e*n];
  let x = 0, z = 0;
  for (let i=0;i<6;i++){ x += t.x[i]*b[i]; z += t.z[i]*b[i]; }
  return [x, z];
}

/* ── 사업경계 ────────────────────────────────────────────
   지형을 따라가며 얹는다. 지형(표면·지반)이나 과장을 바꾸면 다시 얹는다 */
const BND = (D.bnd || []).map(r => r.map(([E, N]) => {
  const p = toScene(E, N);
  return [p[0], p[1], E, N];
}));
let bndOn = true, bndObj = null;
function hAt(x, z){                       // 화면 좌표에서 지형 높이(과장 전)
  const col = Math.round((x + wm/2)/MPP), row = Math.round((z + hm/2)/MPP);
  if (col < 0 || col >= W || row < 0 || row >= H) return null;
  return HS[which][row*W + col]/10 - D.base;
}
function drawBnd(){
  if (bndObj){ scene.remove(bndObj); bndObj.geometry.dispose(); bndObj = null; }
  if (!bndOn || !BND.length) { return; }
  const segs = [];
  for (const ring of BND){
    for (let i=0;i<ring.length;i++){
      const a = ring[i], b = ring[(i+1)%ring.length];
      const ya = hAt(a[0], a[1]), yb = hAt(b[0], b[1]);
      if (ya === null || yb === null) continue;
      segs.push(a[0], ya*ex + 1.2, a[1], b[0], yb*ex + 1.2, b[1]);   // 1.2m 띄워 파묻히지 않게
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(segs), 3));
  bndObj = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({color:0xff3b30}));
  bndObj.renderOrder = 2;
  scene.add(bndObj);
}
document.getElementById('bBnd').onclick = () => {
  bndOn = !bndOn;
  document.getElementById('bBnd').classList.toggle('on', bndOn);
  drawBnd(); render();
};
document.getElementById('bRe').onclick = () => location.reload();

/* ── 키맵 ────────────────────────────────────────────────
   사업지구 어디를 보고 있는지 작은 지도로 보여 준다.
   경계는 한 번만 그려 두고(밑그림), 매 번은 보는 자리와 시야만 덧그린다 */
const KM = {
  on:true, cv:document.getElementById('keymap'), base:null, sx:1, ox:0, oy:0,
  init(){
    const w = this.cv.width, h = this.cv.height, pad = 10;
    let x0=1e9, x1=-1e9, z0=1e9, z1=-1e9;
    for (const r of BND) for (const p of r){
      x0=Math.min(x0,p[0]); x1=Math.max(x1,p[0]); z0=Math.min(z0,p[1]); z1=Math.max(z1,p[1]); }
    if (!isFinite(x0)) { x0=-wm/2; x1=wm/2; z0=-hm/2; z1=hm/2; }
    this.sx = Math.min((w-pad*2)/(x1-x0), (h-pad*2)/(z1-z0));
    this.ox = pad - x0*this.sx + ((w-pad*2)-(x1-x0)*this.sx)/2;
    this.oy = pad - z0*this.sx + ((h-pad*2)-(z1-z0)*this.sx)/2;
    this.base = document.createElement('canvas');
    this.base.width = w; this.base.height = h;
    const c = this.base.getContext('2d');
    c.strokeStyle = '#ff3b30'; c.lineWidth = 1.4; c.lineJoin = 'round';
    for (const r of BND){
      c.beginPath();
      r.forEach((p,i) => { const X=p[0]*this.sx+this.ox, Y=p[1]*this.sx+this.oy;
        i ? c.lineTo(X,Y) : c.moveTo(X,Y); });
      c.closePath(); c.stroke();
    }
    c.fillStyle = 'rgba(255,59,48,.10)'; c.fill();
  },
  draw(){
    if (!this.on) return;
    if (!this.base) this.init();
    const g = this.cv.getContext('2d');
    g.clearRect(0,0,this.cv.width,this.cv.height);
    g.drawImage(this.base,0,0);
    const tx = target.x*this.sx+this.ox, ty = target.z*this.sx+this.oy;
    const cx = camera.position.x*this.sx+this.ox, cz = camera.position.z*this.sx+this.oy;
    const a = Math.atan2(ty-cz, tx-cx), half = 0.42, len = Math.max(16, Math.hypot(tx-cx, ty-cz));
    g.fillStyle = 'rgba(0,208,164,.22)'; g.strokeStyle = '#00d0a4'; g.lineWidth = 1;
    g.beginPath(); g.moveTo(cx,cz);
    g.lineTo(cx+Math.cos(a-half)*len, cz+Math.sin(a-half)*len);
    g.lineTo(cx+Math.cos(a+half)*len, cz+Math.sin(a+half)*len);
    g.closePath(); g.fill(); g.stroke();
    g.fillStyle = '#00d0a4';
    g.beginPath(); g.arc(tx,ty,3,0,6.284); g.fill();
    g.fillStyle = '#9aa4ad'; g.font = '10px -apple-system,sans-serif';
    g.fillText('보는 자리', 8, this.cv.height-7);
  }
};
document.getElementById('bMap').onclick = () => {
  KM.on = !KM.on;
  document.getElementById('bMap').classList.toggle('on', KM.on);
  KM.cv.style.display = KM.on ? 'block' : 'none';
  KM.draw();
};

document.getElementById('ex').oninput = e => {
  ex = +e.target.value; document.getElementById('exv').textContent = ex.toFixed(1)+'×';
  apply(); drawBnd(); render(); };
function pick(w){
  which = w;
  document.getElementById('bSurf').classList.toggle('on', w==='표면');
  document.getElementById('bGnd').classList.toggle('on', w==='지반');
  apply(); drawBnd(); render();
}
document.getElementById('cPhoto').onclick = () => setMode('photo');
document.getElementById('cObj').onclick = () => setMode('obj');
document.getElementById('cCls').onclick = () => setMode('cls');
document.getElementById('bSurf').onclick = () => pick('표면');
document.getElementById('bGnd').onclick = () => pick('지반');
document.getElementById('bReset').onclick = () => {
  target.set(0,0,0); dist=wm*0.95; yaw=-0.6; pitch=0.72; render(); };
document.getElementById('bTop').onclick = () => { pitch = 1.5; yaw = 0; render(); };
document.getElementById('bTilt').onclick = () => { pitch = 0.28; render(); };
apply();
</script>
<!--__MEASURE__-->
</body></html>
"""


def main():
    cfg = config.load()
    tm = TM(**cfg["crs"])
    OUT, WORK, DATA = cfg["output_dir"], cfg["work_dir"], cfg["data_dir"]
    v3 = cfg["view_3d"]
    dem = os.path.join(WORK, "dem.json")
    gndp = os.path.join(WORK, "지반고.json")
    if not os.path.exists(dem):
        sys.exit(f"표면 표고 격자가 없습니다: {dem}\n  tiles_nogdal.py 또는 build_dsm.sh 를 먼저 돌리십시오")
    if not os.path.exists(gndp):
        print("  ⚠ 지반고.json 이 없어 표면을 지반으로도 씁니다(지반 단추가 표면과 같아집니다)")
        gndp = dem
    box = cfg["crop_box"]
    if not box:
        sys.exit("입체지도는 설정의 crop_box(평면직각좌표 범위)가 필요합니다")
    tex, (w, h), bounds, mpp = stitch(os.path.join(OUT, "tiles"), merc_bounds(tm, box),
                                      v3["tex_zoom"], v3["max_side"], v3["jpeg_quality"])
    step = v3["step"]
    gw, gh = w // step, h // step
    surf, s0, _ = height(dem, bounds, gw, gh, "표면")
    gnd, g0, _ = height(gndp, bounds, gw, gh, "지반")
    bld = building_mask(os.path.join(DATA, "현황건물.json"), bounds, gw, gh)
    wm = (gw - 1) * mpp * step
    hm = (gh - 1) * mpp * step
    tm2s = tm_to_scene(tm, box, bounds, wm, hm)
    bnd = boundary(tm, os.path.join(DATA, "base.json"))
    data = {"w": gw, "h": gh, "mpp": mpp, "step": step, "base": round(min(s0, g0), 1),
            "surf": surf, "gnd": gnd, "bld": bld, "tm2s": tm2s, "bnd": bnd, "tex": tex}
    lab = cfg["labels"]
    html = HTML.replace("/*__THREE__*/", open(os.path.join(ROOT, "lib", "three.min.js"),
                                             encoding="utf-8").read(), 1)
    html = html.replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False), 1)
    html = html.replace("<!--__MEASURE__-->", measure_tool.payload(DATA, cfg["crs"].get("epsg", 5186)), 1)
    for tok, val in [("/*__TITLE__*/", cfg["title"]), ("/*__FOOTER__*/", cfg["footer"]),
                     ("/*__BUILD__*/", datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
                     ("/*__SURFACE_NOTE__*/", lab.get("surface_note", "")),
                     ("/*__GROUND_NOTE__*/", lab.get("ground_note", ""))]:
        html = html.replace(tok, val)
    os.makedirs(OUT, exist_ok=True)
    out_html = os.path.join(OUT, "입체지도.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(OUT, "한글확인.js"), "w", encoding="utf-8") as f:
        f.write("window.__KO=1;\n")                  # 윈도우 탐침용
    print(f"{out_html} {len(html)/1048576:.1f}MB")


if __name__ == "__main__":
    main()
