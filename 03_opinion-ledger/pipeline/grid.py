# -*- coding: utf-8 -*-
"""PDF 표 그리드 복원.

한컴 PDF는 행 구분선을 점선(짧은 조각 수백 개)으로 그린다. pdfplumber 기본
설정은 이를 선으로 인식하지 못해 여러 행을 한 셀로 합쳐버린다. 여기서는
조각을 좌표별로 뭉쳐 실제 괘선을 복원하고, 병합셀(rowspan/colspan)까지
반영한 2차원 그리드를 만든다.
"""
from collections import defaultdict

import cfg

_P = cfg.P
HMIN = float(_P.get("hline_min_len", 30.0))
HGAP = float(_P.get("hline_merge_gap", 2.0))
YTOL = float(_P.get("hline_ytol", 1.0))
VMIN = float(_P.get("vline_min_len", 10.0))
VGAP = float(_P.get("vline_merge_gap", 3.0))
XTOL = float(_P.get("vline_xtol", 1.0))
VFRAC = float(_P.get("col_min_height_frac", 0.3))
LINE_BUCKET = float(_P.get("char_line_bucket", 8.0))   # 글자 중심 y를 이 값의 절반 단위로 묶어 줄을 가른다
SPACE_GAP = float(_P.get("space_gap", 1.6))            # 글자 사이가 이보다 벌어지면 띄어쓰기로 본다


def _merge(iv, gap):
    iv = sorted(iv)
    out = []
    for a, b in iv:
        if out and a - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def hlines(page, min_len=HMIN, ytol=YTOL):
    """수평 괘선 → [(y, [(x0,x1),...])]"""
    buckets = defaultdict(list)
    for e in page.edges:
        if e["orientation"] == "h":
            buckets[round(e["top"] / ytol) * ytol].append((e["x0"], e["x1"]))
    out, prev = [], None
    for y in sorted(buckets):
        if prev is not None and y - prev[0] <= ytol:
            prev[1].extend(buckets[y])
        else:
            prev = [y, list(buckets[y])]
            out.append(prev)
    res = []
    for y, iv in out:
        segs = [s for s in _merge(iv, HGAP) if s[1] - s[0] >= min_len]
        if segs:
            res.append((y, segs))
    return res


def vlines(page, min_len=VMIN, xtol=XTOL):
    """수직 괘선 → [(x, [(y0,y1),...])]"""
    buckets = defaultdict(list)
    for e in page.edges:
        if e["orientation"] == "v":
            buckets[round(e["x0"] / xtol) * xtol].append((e["top"], e["bottom"]))
    out, prev = [], None
    for x in sorted(buckets):
        if prev is not None and x - prev[0] <= xtol:
            prev[1].extend(buckets[x])
        else:
            prev = [x, list(buckets[x])]
            out.append(prev)
    res = []
    for x, iv in out:
        segs = [s for s in _merge(iv, VGAP) if s[1] - s[0] >= min_len]
        if segs:
            res.append((x, segs))
    return res


def cell_text(page, x0, x1, top, bottom, pad=0.5, chars=None):
    """글자 중심 기준 배정. 양쪽 정렬로 칸 경계에 붙어 한 단어로 뭉친 글자('가나○')도 정확히 분리."""
    src = chars if chars is not None else page.chars
    cs = [c for c in src
          if x0 - pad <= (c["x0"] + c["x1"]) / 2 <= x1 + pad
          and top - pad <= (c["top"] + c["bottom"]) / 2 <= bottom + pad]
    if not cs:
        return ""
    lines = defaultdict(list)
    for c in cs:
        # 글자 중심으로 줄을 가른다. 윗변(top) 기준이면 한자·작은 글자가 윗줄로 튀어
        # 엉뚱한 자리에 끼어든다(괄호 안 한자 약칭이 앞줄 문장 중간에 박히던 사례).
        lines[round((c["top"] + c["bottom"]) / LINE_BUCKET)].append(c)
    out = []
    for k in sorted(lines):
        ln = sorted(lines[k], key=lambda c: c["x0"])
        buf, prev = [], None
        for c in ln:
            if prev is not None and c["x0"] - prev > SPACE_GAP:
                buf.append(" ")
            buf.append(c["text"])
            prev = c["x1"]
        s = "".join(buf).strip()
        if s:
            out.append(s)
    return "\n".join(out).strip()


class Grid:
    """괘선으로 복원한 표. cells[r][c] = 병합 반영된 텍스트, spans[r][c] = (r0,c0) 원점"""

    def __init__(self, page, min_hlen=HMIN, vfrac=VFRAC):
        self.page = page
        self.chars = page.chars
        hs = hlines(page, min_len=min_hlen)
        vs = vlines(page)
        self.ok = len(hs) >= 2 and len(vs) >= 2
        if not self.ok:
            return
        self.ys = [y for y, _ in hs]
        self.hsegs = {y: sg for y, sg in hs}
        y0, y1 = self.ys[0], self.ys[-1]
        H = y1 - y0
        # 표 전체 높이의 일정 비율 이상 뻗은 수직선만 열 경계로 인정(중첩표 괘선 배제)
        self.xs = [x for x, sg in vs if max(b - a for a, b in sg) >= vfrac * H]
        self.vsegs = {x: sg for x, sg in vs}
        self.nr = len(self.ys) - 1
        self.nc = len(self.xs) - 1
        self.ok = self.nr >= 1 and self.nc >= 2
        if self.ok:
            self._build()

    def _cov(self, segs, a, b):
        m = (a + b) / 2
        return any(s0 - 1 <= m <= s1 + 1 for s0, s1 in segs)

    def _has_top(self, r, c):
        return self._cov(self.hsegs[self.ys[r]], self.xs[c], self.xs[c + 1])

    def _has_left(self, r, c):
        x = self.xs[c]
        return self._cov(self.vsegs.get(x, []), self.ys[r], self.ys[r + 1])

    def _build(self):
        self.cells = [[None] * self.nc for _ in range(self.nr)]
        self.origin = [[None] * self.nc for _ in range(self.nr)]
        for r in range(self.nr):
            for c in range(self.nc):
                if self.origin[r][c] is not None:
                    continue
                # 병합 영역 확장: 오른쪽은 좌측 괘선이 없는 동안, 아래는 상단 괘선이 없는 동안
                c2 = c
                while c2 + 1 < self.nc and not self._has_left(r, c2 + 1):
                    c2 += 1
                r2 = r
                while r2 + 1 < self.nr and not any(self._has_top(r2 + 1, cc) for cc in range(c, c2 + 1)):
                    r2 += 1
                txt = cell_text(self.page, self.xs[c], self.xs[c2 + 1],
                                self.ys[r], self.ys[r2 + 1], chars=self.chars)
                for rr in range(r, r2 + 1):
                    for cc in range(c, c2 + 1):
                        self.cells[rr][cc] = txt
                        self.origin[rr][cc] = (r, c)

    def row_bounds(self, r):
        return self.ys[r], self.ys[r + 1]
