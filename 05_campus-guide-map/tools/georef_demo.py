#!/usr/bin/env python3
"""
도면 지리참조(georef) 시연: 지번 글자 위치를 기준점으로 삼아 좌표 없는 벡터 PDF 도면을 지도에 맞춘다

배경
    인허가 도서의 도면 PDF에는 좌표계·좌표값이 적혀 있지 않은 경우가 많다.
    그러나 CAD에서 뽑은 벡터 PDF라면 지적도의 지번 글자가 ｢위치를 가진 텍스트｣로 남아 있다.
    지번별 실제 좌표(편입 필지 목록을 지오코딩한 값 등)와 지번을 짝지으면
    도면 좌표 → 실세계 좌표 아핀 변환을 복원할 수 있다.
    같은 도곽(frame)으로 출력한 토지이용계획도에 그 변환을 그대로 적용해 용도별 폴리곤을 뽑는다.

이 스크립트는 실제 도면 대신 가상 예시로 전 과정을 재현한다.
    make   : 예시자료(data/sample)로 ｢좌표 없는｣ 합성 도면 PDF 2장과 가상 지번 좌표 CSV를 만든다.
             도면에는 모르는 회전·축척·원점이 걸려 있고, CSV에는 측위 잡음과 틀린 좌표(이상치)가 섞여 있다.
    run    : 합성 도면만 보고 변환을 복원해 GeoJSON을 뽑고, 면적 검산과 위치 검산을 한다.
    run --flip : 흔한 실수(pdfplumber 의 y 를 한 번 더 뒤집기)를 재현한다.
             면적 검산은 통과하는데 위치 검산에서 걸린다는 것을 보여 준다.

절차 (run)
    1) 지적도 PDF 글자를 문자 행렬(matrix) 기준으로 이어 붙여 지번 문자열 복원
       (CAD 텍스트는 글자마다 따로 놓여 있어 일반 텍스트 추출로는 깨진다)
    2) 도면에 한 번만 나오고 CSV에도 한 번만 있는 지번만 기준점으로 채택
    3) RANSAC 아핀 적합: 무작위 3점으로 변환을 세우고, 가장 많은 점이 맞는 해를 고른 뒤 재적합
    4) 토지이용계획도의 채움 도형을 범례 색으로 용도별 분류, 흰 바탕 합집합 = 구역계
    5) 도로는 채색이 없으므로 (구역계 - 나머지 용도) 차집합
    6) 면적 검산(계획 면적과 대조)과 위치 검산(기준점이 구역계 안에 드는 비율)을 따로 한다

의존
    pdfplumber, numpy, shapely, PyMuPDF(make 에서 PDF 작성)

사용
    python3 tools/georef_demo.py make
    python3 tools/georef_demo.py run
    python3 tools/georef_demo.py run --flip
"""
import argparse
import collections
import csv
import json
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SAMPLE = os.path.join(ROOT, "data", "sample")
DEMO = os.path.join(ROOT, "data", "georef_demo")
PDF_CAD = os.path.join(DEMO, "demo_cadastral.pdf")
PDF_LU = os.path.join(DEMO, "demo_landuse.pdf")
CSV_PTS = os.path.join(DEMO, "demo_parcel_points.csv")
OUT = os.path.join(ROOT, "output", "georef_landuse.geojson")

PAGE_W, PAGE_H = 1190.55, 841.89       # A3 가로(pt)
M_PER_PT = 0.0254 / 72 * 5000          # 1:5,000 에서 도면 1pt 의 실제 길이(m)
LEGEND_BAND_TOP = 760                  # 이 아래는 범례·표제란이라 도형 추출에서 뺀다
SNAP = 0.05                            # 낱장 도형 사이 미세한 틈을 메우는 거리(m)
MLAT = 111132.95

# 합성 도면에 몰래 건 변환(정답). run 은 이 값을 모르는 채로 복원해야 한다
TRUTH = {"rot_deg": 0.35, "origin_pt": (330.0, 690.0)}


def mlng(lat0):
    return 111320.0 * math.cos(math.radians(lat0))


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def load_sample():
    lu = json.load(open(os.path.join(SAMPLE, "landuse.geojson"), encoding="utf-8"))
    plan = json.load(open(os.path.join(SAMPLE, "plan.json"), encoding="utf-8"))
    return lu, plan


# ── make: 합성 도면과 가상 지번 좌표 ───────────────────────────────────────
def make():
    import fitz  # PyMuPDF
    lu, _ = load_sample()
    site = [f for f in lu["features"] if f["properties"]["용도"] == "구역계"][0]
    ring = site["geometry"]["coordinates"][0]
    lat0, lon0 = ring[0][1], ring[0][0]            # 남서 모서리를 미터 원점으로
    ml = mlng(lat0)

    def ll_to_m(lon, lat):
        return (lon - lon0) * ml, (lat - lat0) * MLAT

    th = math.radians(TRUTH["rot_deg"])
    ox, oy = TRUTH["origin_pt"]

    def m_to_pt(e, n):
        # 도면을 살짝 돌리고 1:5,000 으로 줄여 종이 위 원점에 놓는다. PDF 화면 좌표는 y 가 아래로 커진다
        u = (math.cos(th) * e + math.sin(th) * n) / M_PER_PT
        v = (-math.sin(th) * e + math.cos(th) * n) / M_PER_PT
        return ox + u, oy - v

    def ll_to_pt(c):
        return m_to_pt(*ll_to_m(c[0], c[1]))

    os.makedirs(DEMO, exist_ok=True)
    rng = np.random.default_rng(7)

    # 가상 필지: 구역계를 덮는 60m x 50m 격자 중 가운데가 구역계 안인 칸
    site_m = [ll_to_m(*c) for c in ring]

    def inside(pt, poly):
        c, j = False, len(poly) - 1
        for i in range(len(poly)):
            (xi, yi), (xj, yj) = poly[i], poly[j]
            if ((yi > pt[1]) != (yj > pt[1])) and pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi:
                c = not c
            j = i
        return c

    parcels, no = [], 100
    for gy in range(0, 700, 50):
        for gx in range(0, 900, 60):
            cx, cy = gx + 30, gy + 25
            if not inside((cx, cy), site_m):
                continue
            no += 1
            label = str(no) if no % 4 else f"{no - 1}-1"      # 분할 필지 흉내(123-1)
            parcels.append({"label": label, "cell": (gx, gy), "c": (cx, cy)})
    # 같은 지번이 두 번 나오는 경우(다른 리의 같은 번지) 2건 만들기. 대응이 불확실해 배제돼야 한다
    for p in parcels[5:7]:
        p["label"] = "77"

    # 지적도: 필지 경계선 + 지번 글자(글자마다 따로 놓아 CAD 출력 흉내)
    doc = fitz.open()
    pg = doc.new_page(width=PAGE_W, height=PAGE_H)
    for p in parcels:
        gx, gy = p["cell"]
        pts = [m_to_pt(gx, gy), m_to_pt(gx + 60, gy), m_to_pt(gx + 60, gy + 50), m_to_pt(gx, gy + 50)]
        pg.draw_polyline([fitz.Point(*q) for q in pts], color=(0.4, 0.4, 0.4), width=0.3, closePath=True)
        x, y = m_to_pt(*p["c"])
        fs = 5.0
        w = fitz.get_text_length(p["label"], fontname="helv", fontsize=fs)
        cx = x - w / 2
        for ch in p["label"]:
            pg.insert_text((cx, y + fs * 0.35), ch, fontsize=fs, fontname="helv")
            cx += fitz.get_text_length(ch, fontname="helv", fontsize=fs)
    pg.insert_text((40, 800), "DEMO CADASTRAL MAP  1:5000  (synthetic, no coordinates)", fontsize=9)
    doc.save(PDF_CAD)

    # 토지이용계획도: 같은 도곽. 흰 바탕(구역계) 위에 용도별 채움. 도로는 채색하지 않는다
    doc = fitz.open()
    pg = doc.new_page(width=PAGE_W, height=PAGE_H)
    pg.draw_polyline([fitz.Point(*ll_to_pt(c)) for c in ring[:-1]], color=None, fill=(1, 1, 1),
                     closePath=True)
    legend = []
    for f in lu["features"]:
        use = f["properties"]["용도"]
        if use in ("구역계", "도로"):
            continue
        rgb = hex_rgb(f["properties"]["색상"])
        legend.append(rgb)
        polys = [f["geometry"]["coordinates"]] if f["geometry"]["type"] == "Polygon" \
            else f["geometry"]["coordinates"]
        for poly in polys:
            pg.draw_polyline([fitz.Point(*ll_to_pt(c)) for c in poly[0][:-1]], color=None, fill=rgb,
                             closePath=True)
    for i, rgb in enumerate(legend):                   # 범례 칸(추출에서 빠져야 한다)
        pg.draw_rect(fitz.Rect(40 + i * 70, 780, 90 + i * 70, 800), color=None, fill=rgb)
    pg.insert_text((40, 820), "DEMO LAND USE PLAN  1:5000  (same frame as cadastral map)", fontsize=9)
    doc.save(PDF_LU)

    # 가상 지번 좌표: 필지 가운데 + 측위 잡음(약 1m), 일부는 엉뚱한 좌표(이상치)
    with open(CSV_PTS, "w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(["지번", "lat", "lng", "비고"])
        seen77 = 0
        for i, p in enumerate(parcels):
            e, n = p["c"]
            e += rng.normal(0, 1.0)
            n += rng.normal(0, 1.0)
            note = ""
            if i % 13 == 3:                             # 지오코딩이 틀린 필지 흉내
                e += rng.uniform(40, 90) * rng.choice([-1, 1])
                n += rng.uniform(40, 90) * rng.choice([-1, 1])
                note = "이상치(시연용)"
            label = p["label"]
            if label == "77":
                seen77 += 1
                note = "같은 번지가 다른 리에도 있음(시연용)"
            w.writerow([label, round(lat0 + n / MLAT, 7), round(lon0 + e / ml, 7), note])
    print(f"합성 도면 2장 · 가상 필지 {len(parcels)}건")
    print(f"숨겨 둔 정답: 축척 1:5,000 · 회전 {TRUTH['rot_deg']}°")
    print("저장 data/georef_demo/ (demo_cadastral.pdf · demo_landuse.pdf · demo_parcel_points.csv)")


# ── run: 복원 ─────────────────────────────────────────────────────────────
JIBUN = re.compile(r"^(\d{1,4}(?:-\d{1,4})?)$")


def text_runs(chars):
    """글자마다 따로 놓인 텍스트를, 방향(문자 행렬)이 같고 바짝 붙은 것끼리 묶어 원래 문자열로 복원"""
    runs, cur = [], []

    def orient(c):
        m = c["matrix"]
        return (round(m[0], 2), round(m[1], 2))

    for c in chars:
        if cur:
            prev = cur[-1]
            gap = math.hypot(c["x0"] - prev["x1"], c["top"] - prev["top"])
            if orient(c) == orient(prev) and gap < max(c["size"], 0.3) * 2.0:
                cur.append(c)
                continue
            runs.append(cur)
        cur = [c]
    if cur:
        runs.append(cur)
    return runs


def fit_affine():
    import pdfplumber
    with pdfplumber.open(PDF_CAD) as pdf:
        page = pdf.pages[0]
        chars, ph = page.chars, page.height
    labels = collections.defaultdict(list)
    for run in text_runs(chars):
        t = "".join(c["text"] for c in run).strip()
        m = JIBUN.match(t)
        if m:
            x = sum((c["x0"] + c["x1"]) / 2 for c in run) / len(run)
            y = sum((c["top"] + c["bottom"]) / 2 for c in run) / len(run)
            labels[m.group(1)].append((x, y))
    rows = list(csv.DictReader(open(CSV_PTS, encoding="utf-8")))
    by = collections.defaultdict(list)
    for r in rows:
        by[r["지번"]].append((float(r["lat"]), float(r["lng"])))
    # 도면에 한 번, 좌표 목록에도 한 번만 있는 지번이라야 짝이 확실하다
    cps = [(labels[j][0][0], labels[j][0][1], by[j][0][0], by[j][0][1])
           for j in labels if len(labels[j]) == 1 and len(by.get(j, [])) == 1]
    print(f"지번 글자 {sum(len(v) for v in labels.values())}개 복원 · 기준점 후보 {len(cps)}개")
    if len(cps) < 10:
        sys.exit("기준점이 너무 적다")

    lat0 = sum(c[2] for c in cps) / len(cps)
    lon0 = sum(c[3] for c in cps) / len(cps)
    ml = mlng(lat0)
    A = np.array([[c[0], c[1], 1.0] for c in cps])
    E = np.array([(c[3] - lon0) * ml for c in cps])
    N = np.array([(c[2] - lat0) * MLAT for c in cps])

    def solve(idx):
        ce, *_ = np.linalg.lstsq(A[idx], E[idx], rcond=None)
        cn, *_ = np.linalg.lstsq(A[idx], N[idx], rcond=None)
        return ce, cn

    def resid(ce, cn):
        return np.hypot(A @ ce - E, A @ cn - N)

    rng = np.random.default_rng(42)
    idx = np.arange(len(cps))
    best = None
    for _ in range(2000):
        ce, cn = solve(rng.choice(idx, 3, replace=False))
        inl = resid(ce, cn) < 15.0
        if best is None or inl.sum() > best.sum():
            best = inl
    inl = best
    for _ in range(5):
        ce, cn = solve(np.where(inl)[0])
        inl = resid(ce, cn) < 10.0
    ce, cn = solve(np.where(inl)[0])
    r = resid(ce, cn)[inl]
    aff = {"ce": ce.tolist(), "cn": cn.tolist(), "lat0": lat0, "lon0": lon0, "mlat": MLAT, "mlon": ml,
           "기준점_전체": len(cps), "기준점_채택": int(inl.sum()),
           "오차_중앙값_m": round(float(np.median(r)), 2),
           "오차_RMS_m": round(float(math.sqrt((r ** 2).mean())), 2),
           "오차_최대_m": round(float(r.max()), 2),
           "축척_분모": round(math.hypot(ce[0], cn[0]) / (0.0254 / 72)),
           # 도면 가로축·세로축이 실세계에서 돌아간 각의 평균(반시계 +). 도면 y 는 아래로 커진다
           "회전_도": round(math.degrees(math.atan2(cn[0], ce[0]) + math.atan2(ce[1], -cn[1])) / 2, 3)}
    print(f"기준점 {aff['기준점_채택']}/{aff['기준점_전체']} 채택 · 오차 중앙값 {aff['오차_중앙값_m']}m · "
          f"RMS {aff['오차_RMS_m']}m · 최대 {aff['오차_최대_m']}m")
    print(f"복원 축척 1:{aff['축척_분모']:,} · 회전 {aff['회전_도']}°  "
          f"(숨겨 둔 정답 1:5,000 · {TRUTH['rot_deg']}°)")
    return aff


def extract(aff, flip=False):
    import pdfplumber
    from shapely.geometry import Polygon, mapping
    from shapely.ops import unary_union
    lu, _ = load_sample()
    legend = {hex_rgb(f["properties"]["색상"]): f["properties"]["용도"] for f in lu["features"]
              if f["properties"]["용도"] not in ("구역계", "도로")}
    ce, cn = aff["ce"], aff["cn"]

    def to_m(x, y):
        return (ce[0] * x + ce[1] * y + ce[2], cn[0] * x + cn[1] * y + cn[2])

    def classify(color):
        if not isinstance(color, (list, tuple)) or len(color) != 3:
            return None
        if all(abs(v - 1) < 0.01 for v in color):
            return "WHITE"
        best = min(legend, key=lambda k: sum((a - b) ** 2 for a, b in zip(k, color)))
        return legend[best] if sum((a - b) ** 2 for a, b in zip(best, color)) < 0.001 else None

    with pdfplumber.open(PDF_LU) as pdf:
        page = pdf.pages[0]
        ph = page.height
        objs = [o for o in page.curves + page.rects if o.get("fill")]
    by_use, whites = collections.defaultdict(list), []
    for o in objs:
        if (o["top"] + o["bottom"]) / 2 > LEGEND_BAND_TOP:
            continue
        pts = o.get("pts") or [(o["x0"], o["top"]), (o["x1"], o["top"]), (o["x1"], o["bottom"]),
                               (o["x0"], o["bottom"])]
        # 함정: pdfplumber 의 pts 는 이미 위에서 아래로 재는 top 기준이다.
        # PDF 원래 좌표계(아래에서 위)라고 생각해 page.height - y 로 한 번 더 뒤집으면 도형이 상하 반전된다.
        # 뒤집어도 면적은 그대로라 면적 검산은 통과한다. --flip 이 그 실수를 재현한다
        g = Polygon([to_m(x, ph - y if flip else y) for x, y in pts])
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty or g.area < 1:
            continue
        kind = classify(o.get("non_stroking_color"))
        if kind == "WHITE":
            whites.append(g)
        elif kind:
            by_use[kind].append(g)
    # 흰 바탕 낱장 사이 틈을 5cm 팽창·수축으로 메워 구역계를 한 덩어리로
    site = unary_union([g.buffer(SNAP) for g in whites]).buffer(-SNAP)
    if hasattr(site, "geoms"):
        site = max(site.geoms, key=lambda g: g.area)
    merged = {u: unary_union(gs) for u, gs in by_use.items()}
    merged["도로"] = site.difference(unary_union(list(merged.values())))

    def to_ll(geom):
        gm = mapping(geom)

        def walk(c):
            if isinstance(c[0], (int, float)):
                return [round(aff["lon0"] + c[0] / aff["mlon"], 7), round(aff["lat0"] + c[1] / aff["mlat"], 7)]
            return [walk(i) for i in c]
        gm["coordinates"] = walk(gm["coordinates"])
        return gm

    feats = [{"type": "Feature", "properties": {"용도": "구역계", "면적_㎡": round(site.area)},
              "geometry": to_ll(site)}]
    for u, g in sorted(merged.items(), key=lambda kv: -kv[1].area):
        feats.append({"type": "Feature", "properties": {"용도": u, "면적_㎡": round(g.area)},
                      "geometry": to_ll(g)})
    return {"type": "FeatureCollection", "properties": {"자료": "합성 도면에서 복원한 가상 예시"},
            "features": feats}, site, merged


def check(aff, site, merged):
    from shapely.geometry import Point
    _, plan = load_sample()
    ref = {r["구분"]: r["면적_㎡"] for r in plan["용지"]}
    print(f"\n{'용도':<10}{'추출 ㎡':>11}{'계획 ㎡':>11}{'차이 %':>9}")
    rows = [("구역계", site.area, plan["메타"]["총면적_㎡"])] + \
        [(u, g.area, ref.get(u)) for u, g in sorted(merged.items(), key=lambda kv: -kv[1].area)]
    worst = 0.0
    for u, got, want in rows:
        d = (got - want) / want * 100 if want else 0
        worst = max(worst, abs(d))
        print(f"{u:<10}{got:>11,.0f}{(want or 0):>11,}{d:>+9.2f}")
    rows = list(csv.DictReader(open(CSV_PTS, encoding="utf-8")))
    pts = [Point((float(r["lng"]) - aff["lon0"]) * aff["mlon"], (float(r["lat"]) - aff["lat0"]) * aff["mlat"])
           for r in rows]
    # 주의: site 는 미터 좌표다. 경위도를 그대로 넣으면 좌표계가 달라 엉뚱한 비율이 나온다
    inside = sum(1 for p in pts if site.contains(p))
    rate = inside / len(pts) * 100
    print(f"\n면적 검산: 최대 편차 {worst:.2f}%  → {'통과' if worst < 0.5 else '확인 필요'}")
    print(f"위치 검산: 편입 필지 좌표 {len(pts)}건 중 구역계 안 {inside}건 ({rate:.1f}%)  → "
          f"{'통과' if rate >= 90 else '실패: 도형이 뒤집혔거나 어긋남'}")
    return worst, rate


def run(flip):
    if not os.path.exists(PDF_CAD):
        sys.exit("합성 도면이 없다. 먼저 python3 tools/georef_demo.py make")
    if flip:
        print("[--flip] y 축을 한 번 더 뒤집는 실수를 재현한다\n")
    aff = fit_affine()
    gj, site, merged = extract(aff, flip)
    worst, rate = check(aff, site, merged)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(gj, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\n저장 output/georef_landuse.geojson")
    return 0 if (worst < 0.5 and rate >= 90) else 1


def main():
    ap = argparse.ArgumentParser(description="도면 지리참조 시연(가상 예시)")
    ap.add_argument("step", choices=["make", "run"])
    ap.add_argument("--flip", action="store_true", help="y 축 이중 반전 실수 재현")
    a = ap.parse_args()
    if a.step == "make":
        make()
    else:
        sys.exit(run(a.flip))


if __name__ == "__main__":
    main()
