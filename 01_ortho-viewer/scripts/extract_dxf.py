#!/usr/bin/env python3
"""[참고용] 수치지형도 DXF 에서 현황 지형지물을 뽑는다 (자기 자료에 맞게 고쳐 쓰십시오)

  python3 scripts/extract_dxf.py --config config.json
    → {data_dir}/현황건물.json · 도로.json · 구거.json · 표고점.json · 등고선.json

원자료 = 설정의 source.dxf_dir 폴더 안 *.dxf (도엽 여러 장이면 다 읽어 겹친 선을 걸러 낸다)
  ㅇ ⚠ **DWG 말고 DXF 를 쓴다.** GDAL 의 DWG 드라이버(libopencad)는 블록으로 들어 있는 도형을
    풀지 못해 좌표가 0 으로 나온다. 원 사업에서 같은 자료를 DWG 로 읽으면 건물 1,687개·등고선 15줄,
    DXF 로 읽으면 건물 3,105개·등고선 751줄이었다. **도형 수가 적으면 자료가 없는 게 아니라 못 읽은 것일 수 있다**
  ㅇ GDAL 의 DWG 드라이버는 AC1015(R2000) 판만 읽는다. 다른 판은 CAD 프로그램(QCAD 등)에서 DXF 로
    바꾼다. libredwg 의 dwg2dxf 는 빈 껍데기를 낼 때가 있어 권하지 않는다
  ㅇ 한글 층 이름이 깨져 0건이 나오면 환경변수 DXF_ENCODING=UTF-8(또는 CP949)을 준다
  ㅇ 좌표는 설정의 crs(기본 EPSG:5186)라고 보고 위경도로 옮긴다
  ㅇ 층 이름이 곧 수치지형도 지형지물 부호다(국토지리정보원 표준. 판에 따라 다를 수 있으니 확인할 것)
    **B**=건물 · **A**=교통(도로) · **E**=수계(하천·구거)
    **F0017111**=주곡선(1m) · **F0017114**=계곡선(5m) · **F0027132**=표고점(값은 글자에)

⚠ osgeo(GDAL 파이썬)가 든 파이썬으로 돌린다. 원 사업 도엽 28장에서 쓴 것을 설정 기반으로만 바꾸었다.
"""
import glob
import json
import math
import os
import re
import sys

from osgeo import ogr, osr

ogr.UseExceptions()
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config  # noqa: E402

CFG = config.load()
DATA = CFG["data_dir"]
DXF = CFG["source"].get("dxf_dir") or ""
EPSG = int(CFG["crs"]["epsg"])
OUT_BLDG = os.path.join(DATA, "현황건물.json")
OUT_ROAD = os.path.join(DATA, "도로.json")
OUT_WATER = os.path.join(DATA, "구거.json")
OUT_SPOT = os.path.join(DATA, "표고점.json")
OUT_CONT = os.path.join(DATA, "등고선.json")

# 정사영상 타일이 덮는 범위. 이 밖은 배경이 없으니 싣지 않는다(설정 crop_box, 없으면 전부)
BOX = tuple(CFG["crop_box"]) if CFG["crop_box"] else (-1e12, -1e12, 1e12, 1e12)
PAD = 50
LABEL_EVERY = 160.0            # 등고선 위에 표고를 적는 간격(m)


def _tr():
    tm = osr.SpatialReference(); tm.ImportFromEPSG(EPSG)
    wgs = osr.SpatialReference(); wgs.ImportFromEPSG(4326)
    for s in (tm, wgs):
        s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(tm, wgs)


def _inbox(xs, ys):
    return not (max(xs) < BOX[0] - PAD or min(xs) > BOX[2] + PAD
                or max(ys) < BOX[1] - PAD or min(ys) > BOX[3] + PAD)


def sheets():
    files = sorted(glob.glob(os.path.join(DXF, "*.dxf")))
    if not files:
        raise SystemExit(f"DXF 를 못 찾습니다: {DXF}\n  설정 source.dxf_dir 에 DXF 폴더를 적으십시오")
    return files


def walk(pick):
    """도엽을 모두 훑어 pick(층이름) 이 참인 도형을 (층, 꼭짓점목록) 으로 내놓는다.
    블록으로 묶인 도형은 여러 조각(MULTILINESTRING)으로 오므로 낱개로 풀어 준다"""
    for fp in sheets():
        ds = ogr.Open(fp)
        lyr = ds.GetLayer(0)
        ti = lyr.GetLayerDefn().GetFieldIndex("Text")
        for f in lyr:
            code = f.GetField("Layer")
            if not pick(code):
                continue
            g = f.GetGeometryRef()
            if g is None:
                continue
            txt = f.GetField(ti) if ti >= 0 else None
            name = g.GetGeometryName()
            parts = [g] if name in ("LINESTRING", "POINT") else \
                    [g.GetGeometryRef(i) for i in range(g.GetGeometryCount())]
            for p in parts:
                if p is None or p.GetPointCount() < 1:
                    continue
                yield code, [p.GetPoint(k) for k in range(p.GetPointCount())], txt


def lines_of(prefix, tr):
    """앞글자가 prefix 인 층의 선을 위경도로 옮겨 모은다. 도엽이 겹쳐 같은 선이 두 번 오면 하나만 남긴다"""
    lines, by_code, seen, dup = [], {}, set(), 0
    for code, pts, _ in walk(lambda c: c.startswith(prefix)):
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        if not _inbox(xs, ys):
            continue
        key = (code, round(xs[0], 2), round(ys[0], 2), round(xs[-1], 2), round(ys[-1], 2), len(pts))
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        out = []
        for x, y, *_ in pts:
            lon, lat, *_ = tr.TransformPoint(x, y)
            p = [round(lon, 7), round(lat, 7)]
            if not out or p != out[-1]:
                out.append(p)
        if len(out) >= 2:
            lines.append(out)
            by_code[code] = by_code.get(code, 0) + 1
    return lines, by_code, dup


def spots(tr):
    """표고점. 좌표는 도형에, 표고 값은 글자에 들어 있다.
    화면에는 안 띄우지만(누르면 표고가 나온다) 자료로 남긴다"""
    out, bad, seen = [], 0, set()
    for _, pts, txt in walk(lambda c: c == "F0027132"):
        x, y = pts[0][0], pts[0][1]
        t = (txt or "").strip()
        if not re.fullmatch(r"\d{1,3}\.\d", t):
            bad += 1
            continue
        key = (round(x, 2), round(y, 2))
        if key in seen or not _inbox([x], [y]):
            continue
        seen.add(key)
        lon, lat, *_ = tr.TransformPoint(x, y)
        out.append([round(lon, 7), round(lat, 7), float(t)])
    return out, bad


def contours(tr):
    """성과품 등고선. 주곡선 1m(F0017111) · 계곡선 5m(F0017114).
    선을 따라 일정 간격으로 표고 적을 자리도 함께 잡는다"""
    out, labels, seen = [], [], set()
    for code, pts, _ in walk(lambda c: c in ("F0017111", "F0017114")):
        if len(pts) < 3:
            continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        if not _inbox(xs, ys):
            continue
        key = (round(xs[0], 2), round(ys[0], 2), round(xs[-1], 2), round(ys[-1], 2), len(pts))
        if key in seen:
            continue
        seen.add(key)
        h = round(pts[0][2], 1)
        line = []
        for x, y, *_ in pts:
            lon, lat, *_ = tr.TransformPoint(x, y)
            p = [round(lon, 6), round(lat, 6)]        # 약 11cm
            if not line or p != line[-1]:
                line.append(p)
        if len(line) < 3:
            continue
        out.append({"h": h, "p": line})
        labels += label_spots(pts, h, tr)
    return out, labels


def label_spots(pts, h, tr):
    """등고선을 따라가며 일정 간격으로 표고 적을 자리를 잡는다.

    각도는 화면 기준이다(동쪽 x+, 북쪽 y-). 글자가 거꾸로 서지 않도록 90도 안으로 눕힌다.
    선이 짧으면(간격의 절반 미만) 글자를 안 붙인다. 조각마다 붙이면 화면이 숫자로 덮인다
    """
    out = []
    total = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                for i in range(len(pts) - 1))
    if total < LABEL_EVERY * 0.5:
        return out
    marks = [LABEL_EVERY * 0.5 + LABEL_EVERY * k
             for k in range(int((total - LABEL_EVERY * 0.5) / LABEL_EVERY) + 1)]
    run, m = 0.0, 0
    for i in range(len(pts) - 1):
        (x1, y1, *_), (x2, y2, *_) = pts[i], pts[i + 1]
        seg = math.hypot(x2 - x1, y2 - y1)
        while m < len(marks) and marks[m] <= run + seg:
            t = (marks[m] - run) / max(seg, 1e-9)
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            ang = math.degrees(math.atan2(-(y2 - y1), x2 - x1))
            if ang > 90:
                ang -= 180
            elif ang < -90:
                ang += 180
            lon, lat, *_ = tr.TransformPoint(x, y)
            out.append({"h": h, "p": [round(lon, 6), round(lat, 6)], "a": round(ang)})
            m += 1
        run += seg
    return out


def save(path, obj, what):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"  {what:<10} {os.path.getsize(path)/1024:>6.0f}KB  {os.path.basename(path)}")


def main():
    tr = _tr()
    print(f"도엽 {len(sheets())}장을 읽습니다")
    bldg, bcode, bdup = lines_of("B", tr)
    road, rcode, rdup = lines_of("A", tr)
    water, wcode, wdup = lines_of("E", tr)
    spot, bad = spots(tr)
    cont, clab = contours(tr)

    major = sum(1 for c in cont if round(c["h"] * 10) % 50 == 0)
    hs = sorted({c["h"] for c in cont})
    print(f"건물 {len(bldg)} · 도로 {len(road)} · 구거 {len(water)} · 표고점 {len(spot)} "
          f"· 등고선 {len(cont)}(계곡선 {major})")
    print(f"겹쳐 들어온 선 {bdup + rdup + wdup}개 걸러냄 · 표고 글자 못 읽은 것 {bad}개")
    if hs:
        print(f"등고선 높이 {hs[0]:.0f}~{hs[-1]:.0f}m · {len(hs)}단 · 표고 글자 {len(clab)}개")
    save(OUT_BLDG, {"선": bldg, "코드별": bcode}, "건물")
    save(OUT_ROAD, {"선": road, "코드별": rcode}, "도로")
    save(OUT_WATER, {"선": water, "코드별": wcode}, "구거")
    save(OUT_SPOT, {"점": spot}, "표고점")
    save(OUT_CONT, {"선": cont, "간격": 1.0, "표": clab}, "등고선")


if __name__ == "__main__":
    main()
