#!/usr/bin/env python3
"""가상 예시자료를 만든다 → sample_data/

  python3 scripts/make_sample_data.py            (결과는 sample_data/ 에 덮어쓴다)

모두 **가상**이다. 실제 사업지구·측량 성과가 아니다.
  ㅇ 자리: EPSG:5186 E 100,000~101,000 · N 450,000~450,800 (서해 해상의 임의 좌표, 실제 육지 아님)
  ㅇ 가상_정사영상.tif  800×640 · 1.25m/화소 · RGB   (밭·길·마을·비닐하우스·숲을 그림으로 합성)
  ㅇ 가상_DSM.tif       400×320 · 2.5m/화소 · 표면 표고(건물·나무 높이 포함)
  ㅇ 가상_지반.tif      400×320 · 2.5m/화소 · 지반 표고(건물·나무 뺀 땅)
  ㅇ vectors/*.json     사업경계·블록·건물·도로·구거·등고선·지적·지장물 (위경도 또는 5186)

난수 씨앗을 고정해 두었으므로 몇 번을 돌려도 같은 자료가 나온다.
필요 패키지: numpy, Pillow
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import geotiff_lite  # noqa: E402
from tmproj import TM  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "sample_data")
VEC = os.path.join(OUT, "vectors")

E0, N0, E1, N1 = 100000.0, 450000.0, 101000.0, 450800.0   # 가상 범위(EPSG:5186)
ORES, DRES = 1.25, 2.5                                    # 정사영상 · 표고 화소 크기(m)
NODATA = -10000
rng = np.random.default_rng(20260918)
tm = TM()

# ── 가상 지물 배치(국지 좌표 u=동, v=북, 단위 m) ─────────────────────────
SITE = [(120, 90), (900, 90), (900, 560), (860, 720), (300, 720), (120, 650)]     # 사업경계
BLOCKS = [("A1", "산업시설", "#ffb74d", (140, 410, 490, 700), 3),
          ("A2", "산업시설", "#ffb74d", (510, 410, 880, 700), 4),
          ("B1", "지원시설", "#ba68c8", (140, 110, 490, 390), 2),
          ("C1", "공원", "#81c784", (510, 110, 700, 390), 1),
          ("D1", "녹지", "#a5d6a7", (710, 110, 880, 390), 1)]
ROADS = [((0, 400), (1000, 400), 8.0), ((500, 0), (500, 800), 7.0)]           # (시작, 끝, 폭)
HILL = (820, 660, 115.0, 9.0)                                                  # 중심 u,v · 반경 · 높이


def ditch_v(u):
    """구거 중심선(북쪽 좌표)"""
    return 280 + 40 * np.sin(u / 150.0)


def make_buildings():
    b = []
    # 마을: 작은 집·창고
    for _ in range(14):
        cu, cv = 230 + rng.uniform(-80, 80), 590 + rng.uniform(-60, 60)
        w, h = rng.uniform(8, 16), rng.uniform(6, 11)
        b.append(dict(cu=cu, cv=cv, w=w, h=h, rot=float(rng.choice([0, 12, -8])), z=float(rng.uniform(3, 6.5)),
                      kind=str(rng.choice(["주택", "창고"])), roof=str(rng.choice(["blue", "red", "gray"]))))
    # 비닐하우스
    for i in range(6):
        b.append(dict(cu=640 + i * 13, cv=200, w=8, h=44, rot=0, z=3.0, kind="비닐하우스", roof="white"))
    # 공장 한 동
    b.append(dict(cu=360, cv=190, w=42, h=26, rot=5, z=9.0, kind="공장", roof="gray"))
    # 사업경계 밖 창고 두 동
    b.append(dict(cu=60, cv=740, w=14, h=10, rot=0, z=4.5, kind="창고", roof="blue"))
    b.append(dict(cu=960, cv=40, w=12, h=9, rot=20, z=4.0, kind="창고", roof="red"))
    # 네 모서리 좌표
    for x in b:
        r = math.radians(x["rot"])
        c, s = math.cos(r), math.sin(r)
        pts = []
        for du, dv in [(-x["w"] / 2, -x["h"] / 2), (x["w"] / 2, -x["h"] / 2),
                       (x["w"] / 2, x["h"] / 2), (-x["w"] / 2, x["h"] / 2)]:
            pts.append((x["cu"] + du * c - dv * s, x["cv"] + du * s + dv * c))
        x["pts"] = pts
    return b


def inside(poly, u, v):
    """점(배열)이 다각형 안인가(짝홀 규칙)"""
    u = np.asarray(u, dtype="float64")
    v = np.asarray(v, dtype="float64")
    res = np.zeros(u.shape, dtype=bool)
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        cond = (y1 > v) != (y2 > v)
        with np.errstate(divide="ignore", invalid="ignore"):
            xin = (x2 - x1) * (v - y1) / (y2 - y1 + 1e-12) + x1
        res ^= cond & (u < xin)
    return res


def shoelace(pts):
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def road_mask(U, V):
    m = np.zeros(U.shape, dtype=bool)
    for (a, b, w) in ROADS:
        if a[1] == b[1]:
            m |= np.abs(V - a[1]) < w / 2
        else:
            m |= np.abs(U - a[0]) < w / 2
    return m


def ground_at(U, V):
    base = 22 + 0.006 * U + 0.004 * V
    hu, hv, hr, hh = HILL
    hill = hh * np.exp(-((U - hu) ** 2 + (V - hv) ** 2) / (2 * hr**2))
    # 밭을 계단식으로 고른 것(밭두렁·단차). 평지 음영기복 시험용
    terr = 0.5 * np.floor(base / 0.5)
    g = 0.35 * base + 0.65 * terr + hill
    d = np.abs(V - ditch_v(U))
    g -= 1.5 * np.clip(1 - d / 4.0, 0, 1)                    # 구거(폭 약 8m, 깊이 1.5m)
    g += 0.3 * road_mask(U, V)                               # 도로는 조금 높다
    return g


def forest_mask(U, V):
    hu, hv, hr, _ = HILL
    return ((U - hu) ** 2 + (V - hv) ** 2) < (hr * 1.05) ** 2


def rasterize_buildings(U, V, blds):
    height = np.zeros(U.shape, dtype="float32")
    roof = np.full(U.shape, -1, dtype="int16")
    for i, b in enumerate(blds):
        m = inside(b["pts"], U, V)
        height[m] = np.maximum(height[m], b["z"])
        roof[m] = i
    return height, roof


def smooth_noise(shape, scale, seed_rng):
    """부드러운 잡음(작은 격자 난수를 늘린 것)"""
    from PIL import Image
    h, w = shape
    sm = seed_rng.random((max(2, h // scale), max(2, w // scale))).astype("float32")
    im = Image.fromarray(sm, mode="F").resize((w, h), Image.BICUBIC)
    return np.asarray(im)


def grid(res):
    w, h = int(round((E1 - E0) / res)), int(round((N1 - N0) / res))
    u = (np.arange(w) + 0.5) * res
    v = (N1 - N0) - (np.arange(h) + 0.5) * res
    return np.meshgrid(u, v)


def hillshade(z, res, az=315, alt=45):
    dzdy, dzdx = np.gradient(z, res)
    slope = np.arctan(np.hypot(dzdx, dzdy))
    aspect = np.arctan2(-dzdx, dzdy)
    a, e = math.radians(az), math.radians(alt)
    return np.clip(np.sin(e) * np.cos(slope) + np.cos(e) * np.sin(slope) * np.cos(a - aspect), 0, 1)


# ── 벡터 도구 ──────────────────────────────────────────────────────
def ll(pts):
    """국지 좌표 목록 -> [[lon, lat], ...]"""
    E = np.array([p[0] for p in pts]) + E0
    N = np.array([p[1] for p in pts]) + N0
    lo, la = tm.inverse(E, N)
    return [[round(float(a), 7), round(float(b), 7)] for a, b in zip(lo, la)]


def tmc(pts):
    return [[round(p[0] + E0, 2), round(p[1] + N0, 2)] for p in pts]


def contours(z, levels, res):
    """마칭 스퀘어로 등고선을 뽑아 이어 붙인다 -> [(h, [(u,v),...]), ...]"""
    H, W = z.shape
    def pt(r, c):             # 격자 칸 가운데 -> 국지 좌표
        return ((c + 0.5) * res, (N1 - N0) - (r + 0.5) * res)
    out = []
    for lv in levels:
        def edge_point(key):
            kind, r, c = key
            if kind == "h":    # (r,c)-(r,c+1)
                a, b = z[r, c], z[r, c + 1]
                t = (lv - a) / (b - a)
                p, q = pt(r, c), pt(r, c + 1)
            else:              # (r,c)-(r+1,c)
                a, b = z[r, c], z[r + 1, c]
                t = (lv - a) / (b - a)
                p, q = pt(r, c), pt(r + 1, c)
            return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
        above = z >= lv
        adj = {}
        for r in range(H - 1):
            for c in range(W - 1):
                k = (above[r, c] << 3) | (above[r, c + 1] << 2) | (above[r + 1, c + 1] << 1) | above[r + 1, c]
                if k == 0 or k == 15:
                    continue
                top, right, bot, left = ("h", r, c), ("v", r, c + 1), ("h", r + 1, c), ("v", r, c)
                table = {1: [(left, bot)], 2: [(bot, right)], 3: [(left, right)], 4: [(top, right)],
                         5: [(left, top), (bot, right)], 6: [(top, bot)], 7: [(left, top)],
                         8: [(left, top)], 9: [(top, bot)], 10: [(top, right), (left, bot)],
                         11: [(top, right)], 12: [(left, right)], 13: [(bot, right)], 14: [(left, bot)]}
                for a, b in table[k]:
                    adj.setdefault(a, []).append(b)
                    adj.setdefault(b, []).append(a)
        used = set()
        for start in list(adj):
            if all((start, n) in used for n in adj[start]):
                continue
            # 끝점(이웃 하나)부터 시작하면 선이 한 줄로 이어진다
            chain = [start]
            cur, prev = start, None
            while True:
                nxt = [n for n in adj[cur] if (cur, n) not in used]
                if not nxt:
                    break
                n = nxt[0]
                used.add((cur, n)); used.add((n, cur))
                chain.append(n)
                prev, cur = cur, n
                if cur == start:
                    break
            if len(chain) >= 3:
                out.append((lv, [edge_point(k) for k in chain]))
    return out


def main():
    os.makedirs(VEC, exist_ok=True)
    blds = make_buildings()

    # ── 표고 두 벌 ──
    U, V = grid(DRES)
    g = ground_at(U, V).astype("float32")
    bh, _ = rasterize_buildings(U, V, blds)
    tree = np.zeros_like(g)
    fm = forest_mask(U, V)
    nz = smooth_noise(g.shape, 4, rng)
    tree[fm] = 6 + 7 * nz[fm]
    hedge = (np.abs(V - 395) < 3) & (U > 560) & (U < 980)            # 도로변 나무줄
    tree[hedge] = np.maximum(tree[hedge], 5.0)
    dsm = (g + np.maximum(bh, tree) + rng.normal(0, 0.04, g.shape)).astype("float32")
    ginfo = dict(x0=E0, y1=N1, res=DRES, epsg=5186, nodata=NODATA)
    geotiff_lite.write(os.path.join(OUT, "가상_DSM.tif"), dsm, **ginfo)
    geotiff_lite.write(os.path.join(OUT, "가상_지반.tif"), g, **ginfo)
    print(f"표고 {g.shape[1]}×{g.shape[0]} · 지반 {g.min():.1f}~{g.max():.1f}m · 표면 최고 {dsm.max():.1f}m")

    # ── 정사영상 ──
    U, V = grid(ORES)
    H, W = U.shape
    img = np.zeros((H, W, 3), dtype="float32")
    # 밭 필지마다 색을 달리하고 이랑 무늬를 넣는다
    palette = np.array([[118, 140, 70], [150, 160, 88], [170, 150, 110], [135, 118, 84],
                        [96, 128, 62], [182, 170, 128]], dtype="float32")
    pid = (np.floor(U / 50).astype(int) * 31 + np.floor(V / 40).astype(int) * 17) % len(palette)
    img[:] = palette[pid]
    rows = 0.5 + 0.5 * np.sin(U * 2 * math.pi / 3.0 + (pid % 2) * V * 0.4)
    img *= (0.9 + 0.1 * rows)[..., None]
    img *= (0.94 + 0.12 * smooth_noise((H, W), 25, rng))[..., None]
    # 숲
    fm = forest_mask(U, V)
    tn = smooth_noise((H, W), 3, rng)
    img[fm] = (np.array([48, 82, 44]) * (0.7 + 0.6 * tn[fm, None]))
    hedge = (np.abs(V - 395) < 3) & (U > 560) & (U < 980)
    img[hedge] = [56, 92, 50]
    # 구거
    d = np.abs(V - ditch_v(U))
    img[d < 3] = [92, 104, 96]
    img[(d >= 3) & (d < 5)] = [110, 120, 80]
    # 도로
    rm = road_mask(U, V)
    img[rm] = [128, 128, 124]
    # 건물 지붕
    _, roof = rasterize_buildings(U, V, blds)
    col = {"blue": [70, 110, 160], "red": [165, 80, 64], "gray": [150, 150, 146], "white": [222, 226, 224]}
    for i, b in enumerate(blds):
        m = roof == i
        c = np.array(col[b["roof"]], dtype="float32")
        if b["kind"] == "비닐하우스":
            stripe = 0.9 + 0.1 * np.sin(V[m] * 2 * math.pi / 2.0)
            img[m] = c * stripe[:, None]
        else:
            img[m] = c
    # 그늘을 살짝 입혀 입체감을 준다
    from PIL import Image
    dsm_up = np.asarray(Image.fromarray(dsm, mode="F").resize((W, H), Image.BILINEAR))
    shade = hillshade(dsm_up, ORES)
    img *= (0.55 + 0.6 * shade)[..., None]
    img = np.clip(img, 0, 255).astype("uint8")
    geotiff_lite.write(os.path.join(OUT, "가상_정사영상.tif"), img, x0=E0, y1=N1, res=ORES, epsg=5186)
    print(f"정사영상 {W}×{H} · {ORES}m/화소")

    # ── 벡터 ──
    site_ll = ll(SITE + [SITE[0]])
    blocks = []
    for name, use, colr, (u0, v0, u1, v1), nlot in BLOCKS:
        ring = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        blocks.append({"type": "Feature",
                       "properties": {"가구": name, "용도": use, "면적_㎡": round(shoelace(ring)),
                                      "획지수": nlot, "색상": colr},
                       "geometry": {"type": "Polygon", "coordinates": [ll(ring + [ring[0]])]}})
    lo, la = tm.inverse(np.array([E0, E1]), np.array([N0, N1]))
    base = {"bounds": [[float(la[0]), float(lo[0])], [float(la[1]), float(lo[1])]],
            "구역계": [{"type": "Feature",
                      "properties": {"용도": "구역계", "면적_㎡": round(shoelace(SITE)), "색상": "#d32f2f"},
                      "geometry": {"type": "Polygon", "coordinates": [site_ll]}}],
            "블록": {"type": "FeatureCollection", "features": blocks}}
    json.dump(base, open(os.path.join(VEC, "base.json"), "w"), ensure_ascii=False)

    json.dump({"선": [ll(b["pts"] + [b["pts"][0]]) for b in blds], "코드별": {"가상": len(blds)}},
              open(os.path.join(VEC, "현황건물.json"), "w"), ensure_ascii=False)
    road_lines = []
    for (a, b, w) in ROADS:
        if a[1] == b[1]:
            road_lines += [ll([(a[0], a[1] - w / 2), (b[0], b[1] - w / 2)]),
                           ll([(a[0], a[1] + w / 2), (b[0], b[1] + w / 2)])]
        else:
            road_lines += [ll([(a[0] - w / 2, a[1]), (b[0] - w / 2, b[1])]),
                           ll([(a[0] + w / 2, a[1]), (b[0] + w / 2, b[1])])]
    json.dump({"선": road_lines, "코드별": {"가상": len(road_lines)}},
              open(os.path.join(VEC, "도로.json"), "w"), ensure_ascii=False)
    us = np.arange(0, 1001, 10.0)
    ditch = [ll([(u, float(ditch_v(u)) + off) for u in us]) for off in (-3, 3)]
    json.dump({"선": ditch, "코드별": {"가상": 2}}, open(os.path.join(VEC, "구거.json"), "w"),
              ensure_ascii=False)

    # 등고선(가상 지반에서 1m 간격)
    Ug, Vg = grid(DRES)
    gz = ground_at(Ug, Vg)
    levels = np.arange(math.ceil(gz.min()), math.floor(gz.max()) + 1, 1.0)
    lines, labels = [], []
    for h, pts in contours(gz, levels, DRES):
        lines.append({"h": float(h), "p": ll(pts)})
        acc, nxt = 0.0, 60.0
        for i in range(1, len(pts)):
            du, dv = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
            acc += math.hypot(du, dv)
            if acc >= nxt:
                a = -math.degrees(math.atan2(dv, du))          # 화면은 아래가 +y
                a = (a + 90) % 180 - 90                        # 거꾸로 서지 않게 접는다
                labels.append({"h": float(h), "p": ll([pts[i]])[0], "a": round(a)})
                nxt += 120.0
    json.dump({"선": lines, "간격": 1.0, "표": labels},
              open(os.path.join(VEC, "등고선.json"), "w"), ensure_ascii=False)
    print(f"등고선 {len(lines)}줄 · 표고 글자 {len(labels)}자리")

    # 지적(가상 필지 50×40m 격자). 소유 구분도 무작위 가상값
    parcels, n = [], 0
    for iu in range(20):
        for iv in range(20):
            u0, v0 = iu * 50, iv * 40
            if u0 >= 1000 or v0 >= 800:
                continue
            ring = [(u0, v0), (u0 + 50, v0), (u0 + 50, v0 + 40), (u0, v0 + 40)]
            cu, cv = u0 + 25, v0 + 20
            n += 1
            jm = "임" if forest_mask(np.array(cu), np.array(cv)) else ("답" if cv < 300 else "전")
            if (iu * 7 + iv * 3) % 11 == 0:
                jm = "대"
            f = {"p": ll(ring), "c": ll([(cu, cv)])[0], "s": round(shoelace(ring)),
                 "j": f"{100 + n}" if n % 3 else f"{100 + n - 1}-1", "m": jm, "리": "가상리"}
            if inside(SITE, np.array(cu), np.array(cv)):
                r = rng.random()
                f["o"] = "국" if r < 0.06 else ("공" if r < 0.12 else "사")
                f["e"] = "전부"
                f["ta"] = f["s"]
            parcels.append(f)
    cad = {"기준": {"도형": "가상 지적(예시)", "조서": "가상 토지조서(예시)",
                  "주의": "소유 구분은 난수로 만든 가상값"},
           "필지": parcels, "셈": {"필지": len(parcels)}}
    json.dump(cad, open(os.path.join(VEC, "지적.json"), "w"), ensure_ascii=False)
    print(f"지적 가상 필지 {len(parcels)}개")

    # 지장물(건물 실측 윤곽과 치수). 측정 도구의 ｢건물｣ 단추가 쓴다. 좌표는 EPSG:5186
    items = []
    struct = {"주택": "블록조", "창고": "경량철골조", "비닐하우스": "파이프조", "공장": "철골조"}
    for b in blds:
        cu = sum(p[0] for p in b["pts"]) / 4
        cv = sum(p[1] for p in b["pts"]) / 4
        area = shoelace(b["pts"])
        long_, short = max(b["w"], b["h"]), min(b["w"], b["h"])
        bearing = (b["rot"] + (0 if b["h"] >= b["w"] else 90)) % 180     # 긴 변의 방위(북 기준)
        inside_site = bool(inside(SITE, np.array(cu), np.array(cv)))
        items.append({"지번": "", "지목": "대", "소재지": "가상리", "물건": b["kind"],
                      "구조": struct[b["kind"]], "종류": b["kind"],
                      "조서면적": round(area * (1 + rng.uniform(-0.02, 0.02)), 1) if inside_site else None,
                      "면적": round(area, 1), "긴변": round(long_, 2), "짧은변": round(short, 2),
                      "방위": round(bearing, 1), "처마": round(b["z"] * 0.85, 2),
                      "용마루": round(b["z"], 2), "부피": round(area * b["z"] * 0.92, 1),
                      "구역내": inside_site, "c": tmc([(cu, cv)])[0], "p": tmc(b["pts"])})
    json.dump({"지장물": items}, open(os.path.join(VEC, "지장물.json"), "w"), ensure_ascii=False)
    print(f"지장물(가상 건물) {len(items)}개")

    tot = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs)
    print(f"\n{OUT}  계 {tot/1048576:.2f}MB")


if __name__ == "__main__":
    main()
