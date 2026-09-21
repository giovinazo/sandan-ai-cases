#!/usr/bin/env python3
"""GDAL 없이 타일·음영기복·표고 격자를 만든다(예시자료·작은 영상용)

  python3 scripts/tiles_nogdal.py --config sample_data/config.json

만드는 것
  ㅇ {output_dir}/tiles/{z}/{x}/{y}.jpg   정사영상 타일(웹메르카토르 XYZ)
  ㅇ {output_dir}/hs/{z}/{x}/{y}.jpg      음영기복 타일(계조를 편 회색, 중립 128)
  ㅇ {work_dir}/dem.json                  표면(DSM) 표고 격자(데시미터 Int16, base64)
  ㅇ {work_dir}/지반고.json               지반 표고 격자(설정에 ground 가 있을 때)

GDAL 경로(make_tiles.sh + build_dsm.sh)와 **같은 모양의 산출물**을 낸다. 뒤 단계(build.py,
build_3d.py)는 어느 쪽으로 만들었는지 가리지 않는다.

⚠ Pillow 로 원본 전체를 메모리에 올린다. 수백 MB 넘는 실제 성과품은 GDAL 경로를 쓰십시오.
필요 패키지: numpy, Pillow
"""
import base64
import json
import math
import os
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config  # noqa: E402
import geotiff_lite  # noqa: E402
from tmproj import TM, lonlat_to_merc, merc_to_lonlat, merc_to_tile, tile_origin, tile_res  # noqa: E402


# ── 표본 추출 ──────────────────────────────────────────────────────
def pyramid(a, valid, levels=8):
    """2배씩 줄인 사본 목록. 작은 배율 타일에서 계단 현상(앨리어싱)을 막는다"""
    out = [(a.astype("float32"), valid.astype("float32"))]
    for _ in range(levels):
        p, v = out[-1]
        h, w = (p.shape[0] // 2) * 2, (p.shape[1] // 2) * 2
        if h < 4 or w < 4:
            break
        p, v = p[:h, :w], v[:h, :w]
        pv = p * (v[..., None] if p.ndim == 3 else v)
        s = pv[0::2, 0::2] + pv[1::2, 0::2] + pv[0::2, 1::2] + pv[1::2, 1::2]
        n = v[0::2, 0::2] + v[1::2, 0::2] + v[0::2, 1::2] + v[1::2, 1::2]
        with np.errstate(invalid="ignore", divide="ignore"):
            q = s / (n[..., None] if p.ndim == 3 else n)
        q = np.nan_to_num(q)
        out.append((q, (n > 0).astype("float32")))
    return out


def sample(level, info, factor, E, N):
    """(E,N) 자리의 값을 쌍선형으로 읽는다 -> (값, 유효)"""
    a, v = level
    res = info["res"] * factor
    col = (E - info["x0"]) / res - 0.5
    row = (info["y1"] - N) / res - 0.5
    H, W = v.shape
    ok = (col >= -0.5) & (row >= -0.5) & (col <= W - 0.5) & (row <= H - 0.5)
    col = np.clip(col, 0, W - 1.0001)
    row = np.clip(row, 0, H - 1.0001)
    c0, r0 = np.floor(col).astype(int), np.floor(row).astype(int)
    fx, fy = col - c0, row - r0
    def g(arr, rr, cc):
        return arr[rr, cc]
    w00, w01 = (1 - fx) * (1 - fy), fx * (1 - fy)
    w10, w11 = (1 - fx) * fy, fx * fy
    vv = [g(v, r0, c0), g(v, r0, c0 + 1), g(v, r0 + 1, c0), g(v, r0 + 1, c0 + 1)]
    wsum = w00 * vv[0] + w01 * vv[1] + w10 * vv[2] + w11 * vv[3]
    ok &= wsum > 0.5
    if a.ndim == 3:
        s = sum(wt[..., None] * vk[..., None] * g(a, rr, cc)
                for wt, vk, (rr, cc) in zip([w00, w01, w10, w11], vv,
                                            [(r0, c0), (r0, c0 + 1), (r0 + 1, c0), (r0 + 1, c0 + 1)]))
        val = s / np.maximum(wsum, 1e-6)[..., None]
    else:
        s = sum(wt * vk * g(a, rr, cc)
                for wt, vk, (rr, cc) in zip([w00, w01, w10, w11], vv,
                                            [(r0, c0), (r0, c0 + 1), (r0 + 1, c0), (r0 + 1, c0 + 1)]))
        val = s / np.maximum(wsum, 1e-6)
    return val, ok


class Source:
    """원본 영상 하나(설정 좌표계). 파일에서 읽거나 배열로 만든다"""
    def __init__(self, path, tm, box, epsg):
        a, info = geotiff_lite.read(path)
        if info["epsg"] and int(info["epsg"]) != int(epsg):
            sys.exit(f"좌표계가 설정(EPSG:{epsg})과 다릅니다: {path} (EPSG:{info['epsg']})")
        self._setup(a, info, tm, box)

    @classmethod
    def from_array(cls, a, info, tm, box):
        self = cls.__new__(cls)
        self._setup(a, info, tm, box)
        return self

    def _setup(self, a, info, tm, box):
        valid = np.ones(a.shape[:2], dtype=bool)
        if a.ndim == 2:
            nod = info["nodata"]
            valid &= np.isfinite(a)
            if nod is not None:
                valid &= a > nod + 1
        self.valid = valid
        self.a, self.info, self.tm, self.box = a, info, tm, box
        self.pyr = pyramid(a, valid)
        H, W = a.shape[:2]
        self.extent = (info["x0"], info["y1"] - H * info["res"], info["x0"] + W * info["res"], info["y1"])

    def at_merc(self, X, Y, px_m):
        """웹메르카토르 좌표 격자의 값. px_m = 한 화소가 땅에서 몇 m 인가"""
        lon, lat = merc_to_lonlat(X, Y)
        E, N = self.tm.forward(lon, lat)
        L = int(max(0, min(len(self.pyr) - 1, math.floor(math.log2(max(px_m / self.info["res"], 1.0))))))
        val, ok = sample(self.pyr[L], self.info, 2**L, E, N)
        if self.box:
            b = self.box
            ok &= (E >= b[0]) & (E <= b[2]) & (N >= b[1]) & (N <= b[3])
        return val, ok


def merc_bounds(tm, box):
    E = np.linspace(box[0], box[2], 9)
    N = np.linspace(box[1], box[3], 9)
    EE, NN = np.meshgrid(E, N)
    lon, lat = tm.inverse(EE.ravel(), NN.ravel())
    x, y = lonlat_to_merc(lon, lat)
    return float(x.min()), float(y.min()), float(x.max()), float(y.max()), float(np.mean(lat))


def make_tiles(src, out_dir, zooms, bounds, mode, quality):
    x0, y0, x1, y1, lat = bounds
    n = 0
    for z in range(zooms[0], zooms[1] + 1):
        tx0, ty0 = merc_to_tile(x0, y1, z)
        tx1, ty1 = merc_to_tile(x1, y0, z)
        res = tile_res(z)
        px_m = res * math.cos(math.radians(lat))
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                ox, oy = tile_origin(tx, ty, z)
                xs = ox + (np.arange(256) + 0.5) * res
                ys = oy - (np.arange(256) + 0.5) * res
                X, Y = np.meshgrid(xs, ys)
                val, ok = src.at_merc(X, Y, px_m)
                if not ok.any():
                    continue
                if mode == "rgb":
                    img = np.zeros((256, 256, 3), dtype="uint8")
                    img[ok] = np.clip(val[ok], 0, 255).astype("uint8")
                    im = Image.fromarray(img, "RGB")
                else:                              # 음영: 자료 밖은 중립 128
                    img = np.full((256, 256), 128, dtype="uint8")
                    img[ok] = np.clip(val[ok], 0, 255).astype("uint8")
                    im = Image.fromarray(img, "L")
                d = os.path.join(out_dir, str(z), str(tx))
                os.makedirs(d, exist_ok=True)
                im.save(os.path.join(d, f"{ty}.jpg"), quality=quality)
                n += 1
    return n


# ── 음영기복(gdaldem hillshade + dsm_tools.py stretch 와 같은 일) ─────────
def hillshade(z, valid, res, zf):
    """여러 방향 그늘의 평균. 값 1~255, 자료 밖 0"""
    zz = np.where(valid, z, np.nan)
    fill = np.nanmedian(zz)
    zz = np.where(valid, z, fill) * zf
    dzdr, dzdc = np.gradient(zz, res)
    p, q = dzdc, -dzdr                            # 동쪽·북쪽 기울기(행은 남쪽으로 증가)
    norm = np.sqrt(1 + p * p + q * q)
    alt = math.radians(45)
    acc = np.zeros_like(zz)
    for az in (225, 270, 315, 360):               # 빛이 오는 방위(북에서 시계 방향)
        a = math.radians(az)
        lx, ly, lz = math.cos(alt) * math.sin(a), math.cos(alt) * math.cos(a), math.sin(alt)
        acc += (-p * lx - q * ly + lz) / norm
    hs = np.clip(acc / 4, 0, 1) * 254 + 1
    hs[~valid] = 0
    return hs


def stretch(hs):
    """중앙값이 128(합성 중립)에 오도록 위·아래를 따로 편다. 평지는 계조가 좁아 그냥 두면 안 보인다"""
    v = hs[hs > 0]
    lo, hi = np.percentile(v, [2, 98])
    mid = np.median(v)
    print(f"  음영 원계조 2% {lo:.0f} · 중앙 {mid:.0f} · 98% {hi:.0f}")
    out = np.where(hs < mid, 20 + (hs - lo) * (128 - 20) / max(mid - lo, 1),
                   128 + (hs - mid) * (236 - 128) / max(hi - mid, 1))
    out = np.clip(out, 0, 255)
    out[hs == 0] = 128                            # 빈값은 중립(0 이면 자료 밖이 시커멓게 덮인다)
    return out.astype("float32")


def grid_json(src, bounds, res, path):
    """웹메르카토르 격자(한 칸 res m)에 표고를 담아 base64 Int16(데시미터)로 저장"""
    x0, y0, x1, y1, lat = bounds
    w = int(math.ceil((x1 - x0) / res))
    h = int(math.ceil((y1 - y0) / res))
    xs = x0 + (np.arange(w) + 0.5) * res
    ys = y1 - (np.arange(h) + 0.5) * res
    X, Y = np.meshgrid(xs, ys)
    val, ok = src.at_merc(X, Y, res * math.cos(math.radians(lat)))
    v = np.clip(np.round(val * 10), -32000, 32000).astype("<i2")
    v[~ok] = -32768
    good = val[ok]
    json.dump({"w": w, "h": h, "x0": float(xs[0]), "y0": float(ys[0]), "res": res,
               "b64": base64.b64encode(v.tobytes()).decode()}, open(path, "w"))
    print(f"  {os.path.basename(path)} {w}×{h} · {good.min():.2f}~{good.max():.2f}m · "
          f"빈칸 {int((~ok).sum())}")


def main():
    cfg = config.load()
    t0 = time.time()
    tm = TM(**cfg["crs"])
    epsg = cfg["crs"]["epsg"]
    out, work = cfg["output_dir"], cfg["work_dir"]
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    src_cfg = cfg["source"]

    ortho = Source(src_cfg["ortho"], tm, cfg["crop_box"], epsg)
    box = cfg["crop_box"] or list(ortho.extent)
    bounds = merc_bounds(tm, box)
    n = make_tiles(ortho, os.path.join(out, "tiles"), cfg["ortho_zoom"], bounds, "rgb", 85)
    print(f"[1] 정사영상 타일 {n}장 (z{cfg['ortho_zoom'][0]}~{cfg['ortho_zoom'][1]})")

    if src_cfg.get("dsm"):
        dsm = Source(src_cfg["dsm"], tm, cfg["crop_box"], epsg)
        hs = stretch(hillshade(dsm.a, dsm.valid, dsm.info["res"], cfg["hs_z_factor"]))
        hsrc = Source.from_array(hs, dict(dsm.info, nodata=None), tm, cfg["crop_box"])
        n = make_tiles(hsrc, os.path.join(out, "hs"), cfg["hs_zoom"], bounds, "gray", 82)
        print(f"[2] 음영기복 타일 {n}장 (z{cfg['hs_zoom'][0]}~{cfg['hs_zoom'][1]})")
        print("[3] 표고 격자")
        grid_json(dsm, bounds, cfg["grid_res_m"], os.path.join(work, "dem.json"))
    else:
        print("[2] DSM 이 설정에 없어 음영기복·표고는 건너뜁니다")
    if src_cfg.get("ground"):
        gnd = Source(src_cfg["ground"], tm, cfg["crop_box"], epsg)
        grid_json(gnd, bounds, cfg["grid_res_m"], os.path.join(work, "지반고.json"))
    print(f"끝 ({time.time() - t0:.1f}초). 다음: python3 scripts/build.py --config {cfg['_path']}")


if __name__ == "__main__":
    main()
