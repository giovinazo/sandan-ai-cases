"""횡메르카토르(TM) 좌표 <-> 위경도 <-> 웹메르카토르(EPSG:3857) 변환 (numpy 만 사용)

GDAL/pyproj 없이 예시 파이프라인을 돌리기 위한 최소 구현이다.
기본값은 EPSG:5186(GRS80, 중부원점 38N 127E, 가산 200,000/600,000, 축척 1.0).
다른 원점(EPSG:5185 서부 125E, 5187 동부 129E, 5188 동해 131E)은 config 의 crs 항목만 바꾸면 된다.

  ㅇ 식은 Snyder(1987) "Map Projections: A Working Manual" 의 TM 급수식
  ㅇ 이 범위(원점에서 수십 km)에서는 GDAL 결과와 mm 단위로 맞는다(verify_tmproj 로 확인)
  ㅇ KGD2002(GRS80) 와 WGS84 는 실무상 같은 자리로 본다
"""
import math

import numpy as np

A = 6378137.0                 # GRS80 장반경
F = 1 / 298.257222101         # GRS80 편평률
R_MERC = 6378137.0            # 웹메르카토르 구 반지름


class TM:
    def __init__(self, lat0=38.0, lon0=127.0, k0=1.0, fe=200000.0, fn=600000.0, **_):
        self.lat0 = math.radians(lat0)
        self.lon0 = math.radians(lon0)
        self.k0 = k0
        self.fe = fe
        self.fn = fn
        self.e2 = F * (2 - F)
        self.ep2 = self.e2 / (1 - self.e2)
        self.m0 = self._m(self.lat0)

    def _m(self, p):
        e2 = self.e2
        return A * ((1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * p
                    - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * np.sin(2 * p)
                    + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * np.sin(4 * p)
                    - (35 * e2**3 / 3072) * np.sin(6 * p))

    def forward(self, lon, lat):
        """위경도(도) -> (E, N) 미터"""
        lon = np.radians(np.asarray(lon, dtype="float64"))
        lat = np.radians(np.asarray(lat, dtype="float64"))
        e2, ep2, k0 = self.e2, self.ep2, self.k0
        s, c, t = np.sin(lat), np.cos(lat), np.tan(lat)
        N = A / np.sqrt(1 - e2 * s * s)
        T = t * t
        C = ep2 * c * c
        Aa = (lon - self.lon0) * c
        M = self._m(lat)
        E = self.fe + k0 * N * (Aa + (1 - T + C) * Aa**3 / 6
                                + (5 - 18 * T + T * T + 72 * C - 58 * ep2) * Aa**5 / 120)
        Nn = self.fn + k0 * (M - self.m0 + N * t * (Aa * Aa / 2
                             + (5 - T + 9 * C + 4 * C * C) * Aa**4 / 24
                             + (61 - 58 * T + T * T + 600 * C - 330 * ep2) * Aa**6 / 720))
        return E, Nn

    def inverse(self, E, Nn):
        """(E, N) 미터 -> 위경도(도)"""
        E = np.asarray(E, dtype="float64")
        Nn = np.asarray(Nn, dtype="float64")
        e2, ep2, k0 = self.e2, self.ep2, self.k0
        M = self.m0 + (Nn - self.fn) / k0
        mu = M / (A * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
        e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
        p1 = (mu + (3 * e1 / 2 - 27 * e1**3 / 32) * np.sin(2 * mu)
              + (21 * e1**2 / 16 - 55 * e1**4 / 32) * np.sin(4 * mu)
              + (151 * e1**3 / 96) * np.sin(6 * mu)
              + (1097 * e1**4 / 512) * np.sin(8 * mu))
        s, c, t = np.sin(p1), np.cos(p1), np.tan(p1)
        C1 = ep2 * c * c
        T1 = t * t
        N1 = A / np.sqrt(1 - e2 * s * s)
        R1 = A * (1 - e2) / (1 - e2 * s * s) ** 1.5
        D = (E - self.fe) / (N1 * k0)
        lat = p1 - (N1 * t / R1) * (D * D / 2
                                    - (5 + 3 * T1 + 10 * C1 - 4 * C1 * C1 - 9 * ep2) * D**4 / 24
                                    + (61 + 90 * T1 + 298 * C1 + 45 * T1 * T1 - 252 * ep2
                                       - 3 * C1 * C1) * D**6 / 720)
        lon = self.lon0 + (D - (1 + 2 * T1 + C1) * D**3 / 6
                           + (5 - 2 * C1 + 28 * T1 - 3 * C1 * C1 + 8 * ep2 + 24 * T1 * T1)
                           * D**5 / 120) / c
        return np.degrees(lon), np.degrees(lat)


def lonlat_to_merc(lon, lat):
    lon = np.asarray(lon, dtype="float64")
    lat = np.asarray(lat, dtype="float64")
    x = np.radians(lon) * R_MERC
    y = np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)) * R_MERC
    return x, y


def merc_to_lonlat(x, y):
    x = np.asarray(x, dtype="float64")
    y = np.asarray(y, dtype="float64")
    lon = np.degrees(x / R_MERC)
    lat = np.degrees(2 * np.arctan(np.exp(y / R_MERC)) - np.pi / 2)
    return lon, lat


WORLD = 2 * math.pi * R_MERC


def tile_res(z):
    """웹메르카토르 z 배율의 화소 크기(m)"""
    return WORLD / (256 * 2**z)


def merc_to_tile(x, y, z):
    n = 2**z
    tx = int((x + WORLD / 2) / WORLD * n)
    ty = int((WORLD / 2 - y) / WORLD * n)
    return tx, ty


def tile_origin(tx, ty, z):
    """타일 왼쪽 위 모서리의 웹메르카토르 좌표"""
    r = tile_res(z) * 256
    return tx * r - WORLD / 2, WORLD / 2 - ty * r


if __name__ == "__main__":
    # 왕복 검사: TM -> 위경도 -> TM
    tm = TM()
    E0, N0 = np.array([100000.0, 200000.0, 228000.0]), np.array([450000.0, 600000.0, 490000.0])
    lo, la = tm.inverse(E0, N0)
    E1, N1 = tm.forward(lo, la)
    print("왕복 오차(m):", np.abs(E1 - E0).max(), np.abs(N1 - N0).max())
