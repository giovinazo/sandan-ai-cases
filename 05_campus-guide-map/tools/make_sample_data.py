#!/usr/bin/env python3
"""
가상 사업지구 예시자료 생성기 (표준 라이브러리만 사용)

실제 사업 자료 대신 쓰는 연습용 자료를 만든다.
임의 위치에 작은 구역계(약 900m x 700m)와 블록 7개를 미터 단위로 설계한 뒤
경위도(WGS84)로 바꾸어 GeoJSON·JSON으로 저장한다.
위치·블록명·용도·면적은 모두 지어낸 값이며 실제 사업과 관계없다.

만들어지는 것 (data/sample/)
    landuse.geojson   구역계 + 용도별 폴리곤(도로는 구역계에서 블록을 뺀 나머지)
    blocks.geojson    블록 경계와 속성(블록명·용도·면적·획지수)
    plan.json         용도별 계획면적·설명 (카드 문구·면적 검산 기준)
    spots.json        로드뷰 대비 지점 3곳

사용
    python3 tools/make_sample_data.py
    python3 tools/make_sample_data.py --lat 36.62 --lng 127.90   # 기준점 바꾸기
"""
import argparse
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "sample")

# 가상 사업지구의 남서쪽 모서리. 아무 의미 없는 임의 위치다
LAT0, LNG0 = 36.6200, 127.9000

COLORS = {
    "산업시설용지": "#bf7fff", "연구시설용지": "#00c8c8", "지원시설": "#ff7fff",
    "공원": "#00c800", "도로": "#f2f2f2", "구역계": "#d32f2f",
}

# 구역계(미터, 남서 모서리 원점). 북동 모서리를 모따기한 오각형
SITE = [(0, 0), (900, 0), (900, 500), (700, 700), (0, 700)]

# 북동 블록은 모따기 선(x+y=1400)에서 20m 안쪽으로 물린다
_c = 1400 - 20 * math.sqrt(2)
BLOCKS = [
    # 블록명, 용도, 획지수, 꼭짓점(미터)
    ("A1", "산업시설용지", 3, [(20, 20), (220, 20), (220, 330), (20, 330)]),
    ("A2", "산업시설용지", 4, [(240, 20), (430, 20), (430, 330), (240, 330)]),
    ("B1", "산업시설용지", 2, [(460, 20), (660, 20), (660, 330), (460, 330)]),
    ("B2", "산업시설용지", 3, [(680, 20), (880, 20), (880, 330), (680, 330)]),
    ("C1", "지원시설", 2, [(20, 360), (200, 360), (200, 680), (20, 680)]),
    ("P1", "공원", 1, [(220, 360), (430, 360), (430, 680), (220, 680)]),
    ("D1", "연구시설용지", 2, [(460, 360), (880, 360), (880, _c - 880),
                              (_c - 680, 680), (460, 680)]),
]

DESC = {
    "산업시설용지": "공장이 들어서는 자리입니다. 업종과 건축 기준은 계획 확정 뒤 달라질 수 있습니다.",
    "연구시설용지": "연구소·시험시설이 들어서는 자리입니다.",
    "지원시설": "식당·편의시설·근로자 지원시설이 모이는 자리입니다.",
    "공원": "근로자와 주민이 쉬는 녹지 공간입니다.",
    "도로": "단지 안 차로와 보도입니다.",
}


def area(ring):
    """신발끈 공식. 미터 좌표 넓이(㎡)"""
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def to_ll(ring, lat0, lng0, ccw=True):
    """미터 → 경위도. GeoJSON 규칙대로 외곽은 반시계, 구멍은 시계 방향으로 닫는다"""
    mlat = 111132.95
    mlng = 111320.0 * math.cos(math.radians(lat0))
    pts = [[round(lng0 + x / mlng, 7), round(lat0 + y / mlat, 7)] for x, y in ring]
    s = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    if (s > 0) != ccw:
        pts.reverse()
    return pts + [pts[0]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=LAT0)
    ap.add_argument("--lng", type=float, default=LNG0)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    site_area = area(SITE)
    blk_feats, by_use = [], {}
    for name, use, lots, ring in BLOCKS:
        ar = round(area(ring))
        by_use.setdefault(use, []).append((name, ring, ar))
        blk_feats.append({
            "type": "Feature",
            "properties": {"블록": name, "용도": use, "면적_㎡": ar, "획지수": lots,
                           "색상": COLORS[use]},
            "geometry": {"type": "Polygon", "coordinates": [to_ll(ring, a.lat, a.lng)]},
        })

    road_area = round(site_area - sum(area(r) for _, _, _, r in BLOCKS))
    lu = [{
        "type": "Feature",
        "properties": {"용도": "구역계", "면적_㎡": round(site_area), "색상": COLORS["구역계"]},
        "geometry": {"type": "Polygon", "coordinates": [to_ll(SITE, a.lat, a.lng)]},
    }]
    for use, items in by_use.items():
        lu.append({
            "type": "Feature",
            "properties": {"용도": use, "면적_㎡": sum(i[2] for i in items), "색상": COLORS[use]},
            "geometry": {"type": "MultiPolygon",
                         "coordinates": [[to_ll(r, a.lat, a.lng)] for _, r, _ in items]},
        })
    # 도로 = 구역계에서 블록을 도려낸 나머지 (구멍 난 폴리곤)
    lu.append({
        "type": "Feature",
        "properties": {"용도": "도로", "면적_㎡": road_area, "색상": COLORS["도로"]},
        "geometry": {"type": "Polygon", "coordinates":
                     [to_ll(SITE, a.lat, a.lng)]
                     + [to_ll(r, a.lat, a.lng, ccw=False) for _, _, _, r in BLOCKS]},
    })

    meta = {"자료": "가상 예시자료. 실제 사업과 관계없음", "좌표계": "WGS84 경위도"}
    json.dump({"type": "FeatureCollection", "properties": meta, "features": lu},
              open(os.path.join(OUT, "landuse.geojson"), "w"), ensure_ascii=False, indent=1)
    json.dump({"type": "FeatureCollection",
               "properties": dict(meta, 설명="블록 경계는 계획 도면에서 옮겨 그린 것으로 가정한 가상 도형"),
               "features": blk_feats},
              open(os.path.join(OUT, "blocks.geojson"), "w"), ensure_ascii=False, indent=1)

    plan_rows = []
    for use in ["산업시설용지", "연구시설용지", "지원시설", "공원", "도로"]:
        ar = road_area if use == "도로" else sum(i[2] for i in by_use[use])
        plan_rows.append({"구분": use, "면적_㎡": ar,
                          "비율_%": round(ar / site_area * 100, 1), "설명": DESC[use]})
    json.dump({"메타": {"총면적_㎡": round(site_area), "기준": "가상 계획(예시)", **meta},
               "용지": plan_rows},
              open(os.path.join(OUT, "plan.json"), "w"), ensure_ascii=False, indent=1)

    mlat = 111132.95
    mlng = 111320.0 * math.cos(math.radians(a.lat))
    spots = []
    for no, (name, x, y, bearing, desc) in enumerate([
        ("남측 진입로", 450, -60, 0, "단지 남쪽 끝 진입로. 정면이 A2·B1 블록"),
        ("서측 농로", -50, 520, 90, "서쪽 경계 밖 농로. 정면이 지원시설 C1"),
        ("북동 모서리", 830, 640, 225, "모따기 된 북동 모서리 밖. 정면이 연구시설 D1"),
    ], 1):
        spots.append({"번호": no, "명": name, "lat": round(a.lat + y / mlat, 6),
                      "lng": round(a.lng + x / mlng, 6), "단지방위_도": bearing, "설명": desc})
    json.dump({"메타": {"용도": "공사 전 현장 모습(로드뷰)과 계획을 견주어 보는 지점", **meta},
               "지점": spots},
              open(os.path.join(OUT, "spots.json"), "w"), ensure_ascii=False, indent=1)

    print(f"구역계 {site_area:,.0f}㎡ · 블록 {len(BLOCKS)}개 · 도로 {road_area:,}㎡")
    print("저장 data/sample/ (landuse.geojson · blocks.geojson · plan.json · spots.json)")


if __name__ == "__main__":
    main()
