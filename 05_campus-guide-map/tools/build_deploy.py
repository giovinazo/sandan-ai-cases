#!/usr/bin/env python3
"""
배포 폴더 생성. https 정적 호스팅(넷리파이·버셀·깃허브 페이지 등)에 폴더째 올리면 된다.

왜 따로 만드는가
    휴대폰의 위치 API(geolocation)와 나침반, 서비스워커(오프라인·홈 화면 추가)는
    https(또는 localhost) 보안 컨텍스트에서만 제대로 동작한다.
    특히 서비스워커는 file:// 에서 등록 자체가 실패한다(origin 'null').
    그래서 단일 HTML 에 서비스워커·매니페스트·아이콘을 곁들인 폴더를 따로 만든다.

만들어지는 것 (기본 dist/web/)
    index.html        자료가 박힌 본체 (web 모드: 서비스워커 등록·새 판 확인)
    sw.js             서비스워커. 화면은 통신 우선, 로컬 타일은 캐시 우선
    manifest.json     홈 화면 추가용
    icon-192.png · icon-512.png · apple-touch-icon.png · favicon.ico  구역계 모양 아이콘
    robots.txt · _headers · vercel.json   404·캐시 설정
    tiles/ · tiles.json   (basemap.choice=local 이고 --tiles 를 준 경우만)

사용
    python3 tools/build_deploy.py
    python3 tools/build_deploy.py --tiles 내타일폴더     # 로컬 타일 동봉(z/x/y 구조)
    python3 -m http.server -d dist/web 8000              # 내 컴퓨터에서 확인

주의
    호스팅 연결 표시 폴더(.vercel, .netlify)는 지우지 않고 남긴다.
    통째로 지우면 다음 배포 때 엉뚱한 새 프로젝트가 생긴다.
    이 폴더들에는 계정·사이트 식별값이 들어 있으므로 저장소에 올리지 않는다(.gitignore).
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_site as BS  # noqa: E402

SW = """/* 안내 지도 서비스워커  판 __BUILD__
   판이 바뀌면 이 파일 내용도 바뀌어야 브라우저가 새 서비스워커를 설치한다(판 표시가 그 역할).
   화면(index.html 등)은 통신 우선: 새 판이 바로 반영되고, 끊기면 캐시로 뜬다.
   같은 주소의 tiles/ 는 캐시 우선: 통신이 끊긴 현장에서도 배경이 뜬다.
   외부 타일 서버(OpenStreetMap 등)는 건드리지 않는다. 대량 저장은 이용 정책 위반이 될 수 있다. */
const SHELL = '__PREFIX__-shell-__BUILD__';
const TILES = '__PREFIX__-tiles-v1';

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL)
    .then(c => c.addAll(['./', './index.html', './manifest.json', './icon-192.png']))
    .then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(
    ks.filter(k => k !== SHELL && k !== TILES).map(k => caches.delete(k))
  )).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.includes('/tiles/')) {
    e.respondWith(caches.match(e.request).then(m => m || fetch(e.request).then(r => {
      if (r.ok) { const c = r.clone(); caches.open(TILES).then(x => x.put(e.request, c)); }
      return r;
    })));
    return;
  }
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok && e.request.method === 'GET') { const c = r.clone(); caches.open(SHELL).then(x => x.put(e.request, c)); }
    return r;
  }).catch(() => caches.match(e.request)));
});
"""

ROBOTS = """# 크롤러가 먼저 찾는 파일. 두어야 404 가 남지 않는다.
# 검색엔진 색인을 막으려면 Allow 를 Disallow 로 바꾼다.
User-agent: *
Allow: /
"""

KEEP = (".vercel", ".netlify")


def prepare(folder):
    """폴더를 비우되 호스팅 연결 표시 폴더는 남긴다"""
    if not os.path.isdir(folder):
        os.makedirs(folder)
        return
    for name in os.listdir(folder):
        if name in KEEP:
            continue
        p = os.path.join(folder, name)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)


def icon_image(cfg, data, size):
    """구역계 모양을 흰색으로 얹은 아이콘. 홈 화면에서 한눈에 구분되도록"""
    from PIL import Image, ImageDraw
    f = cfg["data"]["fields"]
    bval = cfg["data"].get("boundary_value", "구역계")
    geom = [x for x in data["landuse"]["features"] if x["properties"].get(f["use"]) == bval][0]["geometry"]
    ring = geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0]
    xs, ys = [c[0] for c in ring], [c[1] for c in ring]
    pad = size * 0.18
    s = min((size - 2 * pad) / (max(xs) - min(xs)), (size - 2 * pad) / (max(ys) - min(ys)))
    ox = (size - (max(xs) - min(xs)) * s) / 2
    oy = (size - (max(ys) - min(ys)) * s) / 2
    # 화면 y 는 아래로 커진다. 위도는 위로 커지므로 뒤집어 그린다
    pts = [(ox + (c[0] - min(xs)) * s, size - oy - (c[1] - min(ys)) * s) for c in ring]
    img = Image.new("RGB", (size, size), cfg["site"].get("theme_color", "#2e6e64"))
    ImageDraw.Draw(img).polygon(pts, fill="#ffffff")
    return img


def main():
    ap = argparse.ArgumentParser(description="https 정적 호스팅용 배포 폴더 생성")
    ap.add_argument("--config")
    ap.add_argument("--out", help="배포 폴더 (기본: 설정 deploy.out_dir)")
    ap.add_argument("--tiles", help="동봉할 로컬 타일 폴더(z/x/y). basemap.choice=local 일 때")
    a = ap.parse_args()

    cfg = BS.load_config(a.config)
    dep = cfg.get("deploy", {})
    out = a.out or os.path.join(BS.ROOT, dep.get("out_dir", "dist/web"))
    prefix = dep.get("cache_prefix", "guide-map")
    prepare(out)

    build_id = BS.stamp()
    BS.build(cfg, os.path.join(out, "index.html"), web=True, build_id=build_id)
    data = BS.load_data(cfg)

    open(os.path.join(out, "sw.js"), "w", encoding="utf-8").write(
        SW.replace("__BUILD__", build_id.replace(" ", "_")).replace("__PREFIX__", prefix))
    manifest = {
        "name": cfg["site"]["title"], "short_name": cfg["site"].get("short_name", cfg["site"]["title"]),
        "start_url": "./index.html", "display": "standalone", "orientation": "portrait",
        "background_color": "#ffffff", "theme_color": cfg["site"].get("theme_color", "#2e6e64"),
        "lang": "ko",
        "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                  {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"}],
    }
    json.dump(manifest, open(os.path.join(out, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    for size, name in ((192, "icon-192.png"), (512, "icon-512.png"), (180, "apple-touch-icon.png")):
        icon_image(cfg, data, size).save(os.path.join(out, name))
    # 선언이 없어도 브라우저·인앱 브라우저가 찾아가는 이름. 없으면 방문마다 404 가 남는다
    icon_image(cfg, data, 64).save(os.path.join(out, "favicon.ico"), format="ICO",
                                   sizes=[(16, 16), (32, 32), (48, 48)])
    open(os.path.join(out, "robots.txt"), "w").write(ROBOTS)
    # 화면은 늘 새로 확인하게(max-age=0), 타일은 하루. 404 에 긴 캐시가 붙는 호스팅이 있어 짧게 둔다
    open(os.path.join(out, "_headers"), "w").write(
        "/*\n  Cache-Control: public, max-age=0, must-revalidate\n"
        "/tiles/*\n  Cache-Control: public, max-age=86400\n")
    json.dump({"headers": [
        {"source": "/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}]},
        {"source": "/tiles/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=86400"}]},
    ]}, open(os.path.join(out, "vercel.json"), "w"), indent=1)

    if a.tiles:
        if cfg["basemap"].get("choice") != "local":
            print("경고: --tiles 를 주었지만 basemap.choice 가 local 이 아니다. 화면은 이 타일을 쓰지 않는다")
        shutil.copytree(a.tiles, os.path.join(out, "tiles"),
                        ignore=shutil.ignore_patterns(".DS_Store", "._*"))
        rel = sorted("./" + os.path.relpath(os.path.join(r, f), out).replace(os.sep, "/")
                     for r, _, fs in os.walk(os.path.join(out, "tiles")) for f in fs)
        json.dump(rel, open(os.path.join(out, "tiles.json"), "w"))
        print(f"타일 {len(rel)}장 동봉")

    n = sum(len(fs) for r, _, fs in os.walk(out) if not any(k in r for k in KEEP))
    kb = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(out) for f in fs) / 1024
    print(f"\n{os.path.relpath(out, BS.ROOT)}  파일 {n}개 · {kb:.0f}KB")
    print("https 정적 호스팅에 이 폴더를 그대로 올린다")


if __name__ == "__main__":
    main()
