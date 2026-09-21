"""작은 GeoTIFF 를 GDAL 없이 쓰고 읽는다(Pillow 사용)

  ㅇ 예시자료처럼 **작고, 회전이 없고, 한 좌표계(EPSG 코드 하나)** 인 GeoTIFF 만 다룬다
  ㅇ 실제 성과품(수 GB, BigTIFF)은 Pillow 로 못 읽는다. 그때는 GDAL 경로(make_tiles.sh, build_dsm.sh)를 쓴다
"""
import numpy as np
from PIL import Image, TiffImagePlugin

Image.MAX_IMAGE_PIXELS = 400_000_000

T_SCALE, T_TIE, T_KEYS, T_NODATA = 33550, 33922, 34735, 42113


def write(path, arr, x0, y1, res, epsg, nodata=None):
    """arr: (H,W) float32 또는 (H,W,3) uint8. (x0, y1) = 왼쪽 위 모서리 좌표, res = 화소 크기(m)"""
    if arr.ndim == 2:
        im = Image.fromarray(arr.astype("float32"), mode="F")
    else:
        im = Image.fromarray(arr.astype("uint8"), mode="RGB")
    ifd = TiffImagePlugin.ImageFileDirectory_v2()
    ifd[T_SCALE] = (float(res), float(res), 0.0)
    ifd.tagtype[T_SCALE] = 12
    ifd[T_TIE] = (0.0, 0.0, 0.0, float(x0), float(y1), 0.0)
    ifd.tagtype[T_TIE] = 12
    # GeoKeyDirectory: 투영좌표계(1) · 화소=면(1) · 투영 EPSG · 단위 미터(9001)
    ifd[T_KEYS] = (1, 1, 0, 4, 1024, 0, 1, 1, 1025, 0, 1, 1, 3072, 0, 1, int(epsg), 3076, 0, 1, 9001)
    ifd.tagtype[T_KEYS] = 3
    if nodata is not None:
        ifd[T_NODATA] = str(nodata)
        ifd.tagtype[T_NODATA] = 2
    im.save(path, tiffinfo=ifd, compression="tiff_deflate")


def read(path):
    """-> (배열, 정보). 정보 = {x0, y1, res, epsg, nodata}. 배열은 (H,W) float32 또는 (H,W,3) uint8"""
    im = Image.open(path)
    tags = im.tag_v2
    sx, sy = tags[T_SCALE][0], tags[T_SCALE][1]
    tie = tags[T_TIE]
    if abs(sx - sy) > 1e-9:
        raise SystemExit(f"가로·세로 화소 크기가 다른 GeoTIFF 는 이 간이 도구가 다루지 않습니다: {path}")
    keys = tags.get(T_KEYS)
    epsg = None
    if keys:
        k = list(keys)
        for i in range(4, len(k), 4):
            if k[i] == 3072:
                epsg = k[i + 3]
    nod = tags.get(T_NODATA)
    info = {"x0": tie[3] - tie[0] * sx, "y1": tie[4] + tie[1] * sy, "res": sx, "epsg": epsg,
            "nodata": float(str(nod).strip("\x00 ")) if nod not in (None, "") else None}
    if im.mode in ("F", "I;16", "I;16S", "I", "I;16B"):
        a = np.asarray(im, dtype="float32")
    else:
        a = np.asarray(im.convert("RGB"), dtype="uint8")
    return a, info
