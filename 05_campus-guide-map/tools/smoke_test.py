#!/usr/bin/env python3
"""
만든 화면을 헤드리스 브라우저로 열어 점검한다 (선택 사항, Playwright 필요)

점검 항목
    1) 스크립트 오류(콘솔 error·pageerror)가 없는가
    2) 가짜 위치(?sim=)를 블록 안에 두면 ｢블록 이름｣과 방향이 카드에 나오는가
    3) 브라우저 위치 권한을 주고 구역 밖 가까운 곳에 두면 ｢경계까지 거리·길찾기｣가 나오는가
    4) 아주 먼 곳이면 지도를 옮기지 않고 거리만 안내하는가
    5) 휴대폰 크기(390x844)에서 탭이 모두 그려지는가

준비
    pip install playwright && python3 -m playwright install chromium

사용
    python3 tools/smoke_test.py                       # output/guide-map.html
    python3 tools/smoke_test.py --html dist/web/index.html
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))


def sample_points(cfg_path=None):
    """예시자료에서 시험 위치를 고른다: 첫 블록 한가운데 · 구역 밖 150m · 멀리 50km"""
    sys.path.insert(0, HERE)
    import build_site as BS
    cfg = BS.load_config(cfg_path)
    data = BS.load_data(cfg)
    f = cfg["data"]["fields"]
    blk = data["blocks"]["features"][0]
    ring = blk["geometry"]["coordinates"][0] if blk["geometry"]["type"] == "Polygon" \
        else blk["geometry"]["coordinates"][0][0]
    lat = sum(p[1] for p in ring[:-1]) / (len(ring) - 1)
    lng = sum(p[0] for p in ring[:-1]) / (len(ring) - 1)
    bnd = [x for x in data["landuse"]["features"]
           if x["properties"].get(f["use"]) == cfg["data"].get("boundary_value", "구역계")][0]
    bring = bnd["geometry"]["coordinates"][0] if bnd["geometry"]["type"] == "Polygon" \
        else bnd["geometry"]["coordinates"][0][0]
    south = min(p[1] for p in bring)
    return {"inside": (lat, lng, blk["properties"][f["block"]]),
            "near": (south - 150 / 111132.95, lng),
            "far": (lat + 0.45, lng)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default=os.path.join(ROOT, "output", "guide-map.html"))
    ap.add_argument("--config")
    a = ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright 가 없다: pip install playwright && python3 -m playwright install chromium")

    url = "file://" + os.path.abspath(a.html)
    pts = sample_points(a.config)
    errors, ok = [], True

    def watch(page):
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

    def card_text(page):
        page.wait_for_function("document.getElementById('card').style.display === 'block'", timeout=5000)
        page.wait_for_timeout(300)
        return page.inner_text("#cardIn")

    def report(name, cond, detail):
        nonlocal ok
        ok &= cond
        print(f"[{'통과' if cond else '실패'}] {name}: {detail}")

    with sync_playwright() as p:
        br = p.chromium.launch()
        # 1·2) 가짜 위치: 블록 안, 방위 45도
        lat, lng, name = pts["inside"]
        ctx = br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        page = ctx.new_page(); watch(page)
        page.goto(f"{url}?sim={lat:.6f},{lng:.6f},45"); page.wait_for_timeout(700)
        page.click("#bLoc")
        t = card_text(page)
        report("블록 안 위치", f"블록 {name}" in t and "북동" in t, " / ".join(t.splitlines()[:4]))
        cone = page.eval_on_selector(".me .cone", "e => e.style.transform")
        report("방향 부채꼴", "rotate(45" in cone, cone)
        tabs = page.eval_on_selector_all("#tabs button", "bs => bs.map(b => b.textContent)")
        for i in range(len(tabs)):
            page.click(f"#tabs button:nth-child({i + 1})")
        report("탭 그리기", len(tabs) >= 3, json.dumps(tabs, ensure_ascii=False))
        page.screenshot(path=os.path.join(ROOT, "output", "smoke_inside.png"))
        ctx.close()

        # 3) 실제 위치 API 경로: 권한 부여 + 구역 밖 가까운 곳
        lat, lng = pts["near"]
        ctx = br.new_context(viewport={"width": 390, "height": 844}, geolocation={"latitude": lat, "longitude": lng},
                             permissions=["geolocation"])
        page = ctx.new_page(); watch(page)
        page.goto(url); page.wait_for_timeout(700)
        page.click("#bLoc")
        page.wait_for_function("document.getElementById('cardIn').innerText.includes('사업구역')", timeout=8000)
        t = page.inner_text("#cardIn")
        report("구역 밖 가까이", "밖" in t and "경계까지" in t, " / ".join(t.splitlines()[:4]))
        ctx.close()

        # 4) 아주 먼 곳
        lat, lng = pts["far"]
        ctx = br.new_context(viewport={"width": 1280, "height": 800}, geolocation={"latitude": lat, "longitude": lng},
                             permissions=["geolocation"])
        page = ctx.new_page(); watch(page)
        page.goto(url); page.wait_for_timeout(700)
        c0 = page.evaluate("map.getCenter().lat")
        page.click("#bLoc")
        t = card_text(page)
        c1 = page.evaluate("map.getCenter().lat")
        report("먼 곳", "멀리" in t and abs(c1 - c0) < 1e-6, " / ".join(t.splitlines()[:3]))
        ctx.close()
        br.close()

    # 타일 서버 접속 실패(오프라인 환경)는 화면 오류가 아니므로 따로 센다
    real = [e for e in errors if "ERR_" not in e and "Failed to load resource" not in e]
    report("콘솔 오류", not real, f"{len(real)}건 " + ("; ".join(real[:3]) if real else ""))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
