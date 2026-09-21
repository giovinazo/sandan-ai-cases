#!/usr/bin/env python3
"""DSM 뒷일 두 가지. `build_dsm.sh` 가 부른다(GDAL 파이썬 바인딩 필요)

  python3 dsm_tools.py stretch 입력.tif 출력.tif
      음영기복의 계조를 늘린다. 중앙값이 128(합성 중립)에 오도록 위·아래를 따로 편다.
      그냥 두면 평지는 175~200 사이에 몰려 있어 정사영상 위에 겹쳐도 보이지 않는다.
  python3 dsm_tools.py grid 입력.tif 출력.json
      표고 격자를 화면 파일에 담을 형태(base64 Int16 데시미터, 빈값 -32768)로 뽑는다.

⚠ osgeo(GDAL 파이썬)가 든 파이썬으로 돌릴 것. 맥 brew 설치라면 brew 쪽 python3 에만 들어 있다.
"""
import base64
import json
import sys

import numpy as np
from osgeo import gdal

gdal.UseExceptions()


def stretch(src, dst):
    ds = gdal.Open(src)
    b = ds.GetRasterBand(1)
    W, H = ds.RasterXSize, ds.RasterYSize
    k = max(1.0, max(W, H) / 2000)                 # 표본은 한 변 2,000 화소 안쪽으로 줄여 읽는다
    smp = b.ReadAsArray(buf_xsize=max(1, int(W / k)), buf_ysize=max(1, int(H / k))).astype("float32")
    v = smp[smp > 0]                               # 0 은 빈값
    lo, hi = np.percentile(v, [2, 98])
    mid = np.median(v)
    print(f"  원계조 2% {lo:.0f} · 중앙 {mid:.0f} · 98% {hi:.0f}")

    o = gdal.GetDriverByName("GTiff").Create(
        dst, W, H, 1, gdal.GDT_Byte,
        options=["TILED=YES", "COMPRESS=DEFLATE", "ZLEVEL=1", "BIGTIFF=YES"])
    o.SetGeoTransform(ds.GetGeoTransform())
    o.SetProjection(ds.GetProjection())
    ob = o.GetRasterBand(1)
    for y in range(0, H, 2048):
        a = b.ReadAsArray(0, y, W, min(2048, H - y)).astype("float32")
        out = np.where(a < mid, 20 + (a - lo) * (128 - 20) / max(mid - lo, 1),
                       128 + (a - mid) * (236 - 128) / max(hi - mid, 1))
        out = np.clip(out, 0, 255)
        # ⚠ 빈값은 0 이 아니라 128(중립). 0 으로 두면 촬영 범위 밖이 시커멓게 덮인다
        #   (곱셈 합성이면 255 가 중립이다. 합성 방식이 바뀌면 중립값도 바뀐다)
        out[a == 0] = 128
        ob.WriteArray(out.astype("uint8"), 0, y)
    o = None
    print(f"  {dst} 완료")


def grid(src, dst):
    ds = gdal.Open(src)
    gt = ds.GetGeoTransform()
    a = ds.GetRasterBand(1).ReadAsArray().astype("float64")
    nod = ds.GetRasterBand(1).GetNoDataValue()
    bad = ~np.isfinite(a) | (a <= (nod + 1 if nod is not None else -9999))
    good = a[~bad]
    print(f"  격자 {a.shape[1]}×{a.shape[0]} · 화소 {gt[1]:.4f}m(메르카토르)")
    print(f"  표고 {good.min():.2f}~{good.max():.2f}m · 평균 {good.mean():.2f}m · 빈값 {int(bad.sum())}개")

    v = np.clip(np.round(a * 10), -32000, 32000).astype("int16")   # 데시미터
    v[bad] = -32768
    with open(dst, "w") as f:
        json.dump({"w": int(a.shape[1]), "h": int(a.shape[0]),
                   "x0": gt[0] + gt[1] / 2,      # 첫 화소 한가운데(메르카토르 X)
                   "y0": gt[3] + gt[5] / 2,      # 첫 화소 한가운데(메르카토르 Y)
                   "res": gt[1],
                   "b64": base64.b64encode(v.astype("<i2").tobytes()).decode()}, f)
    print(f"  {dst} 저장")


if __name__ == "__main__":
    {"stretch": stretch, "grid": grid}[sys.argv[1]](sys.argv[2], sys.argv[3])
