# -*- coding: utf-8 -*-
"""가상 예시 PDF 생성기(한컴 PDF 표 흉내).

sample_data.json(가상 기관·부서·의견)을 읽어 파이프라인이 실제로 부딪히는 한컴 PDF의 특징을
그대로 재현한 PDF를 만든다.

  · 행 구분선을 짧은 점선 조각 수백 개로 그린다(pdfplumber 기본 설정으로는 선이 안 잡힌다)
  · 부서칸·근거법령칸은 여러 행을 세로로 합친 병합칸이다
  · 병합칸이 쪽을 넘으면 글자가 줄 단위로 두 쪽에 갈린다(부서명 조각, 법령명 조각)
  · 한 건이 쪽을 넘어 조치계획이 다음 쪽으로 이어진다
  · 근거법령 칸 없이 협의의견 칸이 왼쪽으로 병합된 행이 있다
  · 재협의가 본협의 표에 '(2차협의)' 표기로 섞여 있다
  · 두 쪽 모아찍기(가로 한 장에 A4 두 쪽)로 내보낸다(설정 sample_layout.two_up)

함께 원문 대조 시연용 가상 회신 공문 PDF 2개를 만든다.
글꼴은 PyMuPDF에 내장된 CJK 글꼴을 쓰므로 따로 설치할 것이 없다.

실행: python3 sample/make_sample_pdf.py
"""
import json
import math
import sys
from pathlib import Path

import fitz  # PyMuPDF

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pipeline"))
import cfg  # noqa: E402

L = cfg.C["sample_layout"]
DATA = json.load(open(HERE / "sample_data.json", encoding="utf-8"))

FONT = fitz.Font("cjk")
FS = L["font_size"]
SFS = L["summary_font_size"]
LH = L["line_height"]
PADY, PADX = L["cell_pad_y"], L["cell_pad_x"]
PW, PH = L["page_width"], L["page_height"]
TOP, BOT = L["margin_top"], L["margin_bottom"]


# ───────────────────────────── 글자 배치 ─────────────────────────────
def tlen(s, fs=FS):
    return FONT.text_length(s, fontsize=fs)


def wrap(text, width, fs=FS):
    """글자 단위 줄나눔(한컴 기본값처럼 어절 중간에서도 끊는다)"""
    out = []
    for para in str(text or "").split("\n"):
        cur = ""
        for ch in para:
            if tlen(cur + ch, fs) > width - 2 * PADX and cur:
                out.append(cur.rstrip())
                cur = "" if ch == " " else ch
            else:
                cur += ch
        if cur.strip():
            out.append(cur.rstrip())
    return out


def chunk(s, n):
    """좁은 부서칸 줄나눔: 이름은 n글자씩, 문서번호는 번호·연도·월일로 끊는다"""
    import re
    m = re.match(r"^(.*?)(-\d+)?(\(\d{4}\.)?(\d{1,2}\.\d{1,2}\.\))?(\(\d차협의\))?$", s)
    name, num, yr, md, cha = m.groups() if m else (s, None, None, None, None)
    lines = [name[i:i + n] for i in range(0, len(name), n)]
    return lines + [x for x in (num, yr, md, cha) if x]


class Page:
    """논리 쪽 하나의 그리기 목록(선·글자). 마지막에 장(sheet)에 옮겨 그린다."""

    def __init__(self, no):
        self.no = no
        self.lines = []        # (x0, y0, x1, y1, dotted)
        self.texts = []        # (x, baseline, text, fs)

    def text(self, x, y_top, s, fs=FS):
        self.texts.append((x, y_top + fs * 0.95, s, fs))

    def hline(self, x0, x1, y, dotted=False):
        self.lines.append((x0, y, x1, y, dotted))

    def vline(self, x, y0, y1):
        if y1 - y0 > 0.5:
            self.lines.append((x, y0, x, y1, False))


def cell_lines(pg, x0, x1, y0, lines, fs=FS, center=False):
    for j, s in enumerate(lines):
        x = (x0 + x1 - tlen(s, fs)) / 2 if center else x0 + PADX
        pg.text(x, y0 + PADY + j * LH + (LH - fs) / 2, s, fs)


# ───────────────────────────── 총괄표 ─────────────────────────────
def draw_summary(pg, y):
    xs = L["cols_summary"]
    rows = DATA["summary"]
    rh = LH + 2 * PADY
    hdr = L["headers_summary"]
    top = y
    pg.hline(xs[0], xs[-1], y)
    for c, h in enumerate(hdr):
        cell_lines(pg, xs[c], xs[c + 1], y, [h], SFS, center=True)
    y += rh
    pg.hline(xs[0], xs[-1], y)
    ys = []
    for r in rows:
        ys.append((y, y + rh))
        y += rh
    bottom = y

    def span(r):                     # 가로 병합 범위(시작열, 끝열)
        if str(r[0]).startswith("@"):
            return (0, 2)
        if str(r[1]).startswith("@"):
            return (1, 2)
        return None

    # 세로 병합: 0열(기관군), 1열(관계기관)
    def key(i, c):
        r = rows[i]
        if c == 0:
            return None if span(r) == (0, 2) else r[0]
        if c == 1:
            return None if span(r) else (r[0], r[1])
        return None

    # 가로선
    for i in range(1, len(rows)):
        y0 = ys[i][0]
        for c in range(len(xs) - 1):
            k1, k2 = key(i - 1, c), key(i, c)
            if k1 is not None and k1 == k2:
                continue                                  # 세로 병합칸 안쪽은 선이 없다
            pg.hline(xs[c], xs[c + 1], y0, dotted=True)
    pg.hline(xs[0], xs[-1], bottom)
    # 세로선
    for c, x in enumerate(xs):
        for i, (y0, y1) in enumerate(ys):
            sp = span(rows[i])
            if sp and sp[0] < c <= sp[1]:
                continue                                  # 가로 병합칸 안쪽
            pg.vline(x, y0, y1)
        pg.vline(x, top, top + rh)
    # 글자
    done = set()
    for i, r in enumerate(rows):
        sp = span(r)
        for c in range(len(xs) - 1):
            if sp and sp[0] < c <= sp[1]:
                continue
            k = key(i, c)
            if k is not None:
                if (c, k) in done:
                    continue
                done.add((c, k))
            v = r[c]
            if sp and c == sp[0]:
                v = str(v)[1:]
                x1 = xs[sp[1] + 1]
            else:
                x1 = xs[c + 1]
            if isinstance(v, int):
                v = str(v) if v else "-"
            if v == "":
                continue
            cell_lines(pg, xs[c], x1, ys[i][0], [str(v)], SFS, center=(c != 9))
    return bottom


# ───────────────────────────── 상세표 ─────────────────────────────
def layout_group(pages, grp):
    """한 기관군을 새 쪽부터 흘려 배치한다. 쪽마다 머리행을 다시 찍는다."""
    role = cfg.ROLE[grp["name"]]
    city = role == "city"
    xs = L["cols_city"] if city else L["cols_4"]
    hdr = L["headers_city"] if city else L["headers_4"]
    c_op = 2 if city else 1
    rows = grp["rows"]

    # 병합칸 묶음 번호: 같은 첫 칸이 이어지면 한 부서칸, 그 안에서 같은 법령이 이어지면 한 법령칸
    dg, lg = [], []
    for i, r in enumerate(rows):
        same = i and rows[i - 1]["col0"] == r["col0"]
        dg.append(dg[-1] if same else i)
        law = r.get("law", "")
        lgood = city and law and law != "-" and not r.get("merge_op_left")
        if lgood and same and rows[i - 1].get("law") == law and not rows[i - 1].get("merge_op_left"):
            lg.append(lg[-1])
        else:
            lg.append(i if (city and not r.get("merge_op_left")) else None)
    dq = {g: chunk(rows[g]["col0"], L["dept_chunk"]) for g in set(dg)}
    lq = {g: (wrap(rows[g].get("law", ""), xs[2] - xs[1]) if rows[g].get("law") else [])
          for g in set(x for x in lg if x is not None)}

    # 병합칸 글자가 칸 안에 다 들어가도록 묶음의 마지막 행 높이를 늘린다(한컴도 칸을 키운다)
    def natural(i):
        r = rows[i]
        x_op0 = xs[1] if r.get("merge_op_left") else xs[c_op]
        return max(1, len(wrap(r["op"], xs[c_op + 1] - x_op0)),
                   len(wrap(r["ac"], xs[c_op + 2] - xs[c_op + 1])), len(wrap(r["st"], xs[-1] - xs[-2])))
    minl = [natural(i) for i in range(len(rows))]
    for gid, q in ((lg, lq), (dg, dq)):
        for g in set(x for x in gid if x is not None):
            idx = [i for i, x in enumerate(gid) if x == g]
            lack = len(q[g]) - sum(minl[i] for i in idx)
            if lack > 0:
                minl[idx[-1]] += lack

    segs = []            # 쪽마다 [(행번호, y0, y1, op줄, ac줄, st줄)]
    state = {}

    def new_page(first=False):
        pg = Page(len(pages) + 1)
        pages.append(pg)
        y = TOP - 30
        if first:
            pg.text(xs[0], y, grp["heading"], 11)
        y = TOP
        hh = LH + 2 * PADY
        for c, h in enumerate(hdr):
            cell_lines(pg, xs[c], xs[c + 1], y, [h], center=True)
        state.update(pg=pg, y=y + hh, top=y, hh=hh)
        segs.append((pg, []))

    new_page(first=True)
    for i, r in enumerate(rows):
        x_op0 = xs[1] if r.get("merge_op_left") else xs[c_op]
        op = wrap(r["op"], xs[c_op + 1] - x_op0)
        ac = wrap(r["ac"], xs[c_op + 2] - xs[c_op + 1])
        st = wrap(r["st"], xs[-1] - xs[-2])
        if r.get("break_before") and segs[-1][1]:
            new_page()
        rem = [op, ac, st]
        first = True
        while True:
            avail = math.floor((PH - BOT - state["y"] - 2 * PADY) / LH)
            need = max(1, *(len(x) for x in rem))
            if first:
                need = max(need, minl[i])
            k = need
            if first and r.get("split_after_lines"):
                k = min(k, r["split_after_lines"])
            k = min(k, avail)
            if k <= 0:
                new_page()
                continue
            part = [x[:k] for x in rem]
            h = k * LH + 2 * PADY
            segs[-1][1].append((i, state["y"], state["y"] + h, part[0], part[1], part[2]))
            state["y"] += h
            rem = [x[k:] for x in rem]
            if first and k < minl[i] and not any(rem):
                rem = [[], [], []]
            first = False
            if not any(rem):
                break
            new_page()

    # 쪽마다 괘선·글자
    for pg, ss in segs:
        if not ss:
            continue
        top, hh = TOP, LH + 2 * PADY
        bottom = ss[-1][2]
        pg.hline(xs[0], xs[-1], top)
        pg.hline(xs[0], xs[-1], top + hh)
        for a, b in zip(ss, ss[1:]):
            ia, ib = a[0], b[0]
            for c in range(len(xs) - 1):
                if c == 0 and dg[ia] == dg[ib]:
                    continue                                   # 부서칸 병합 안쪽
                if city and c == 1 and lg[ia] is not None and lg[ia] == lg[ib]:
                    continue                                   # 법령칸 병합 안쪽
                pg.hline(xs[c], xs[c + 1], b[1], dotted=True)  # 행 구분선 = 점선
        pg.hline(xs[0], xs[-1], bottom)
        for c, x in enumerate(xs):
            pg.vline(x, top, top + hh)
            if city and c == 2:                                # 법령|의견 경계: 병합행은 선이 없다
                for s in ss:
                    if not rows[s[0]].get("merge_op_left"):
                        pg.vline(x, s[1], s[2])
            else:
                pg.vline(x, top + hh, bottom)
        # 행 글자
        for i, y0, y1, op, ac, st in ss:
            x_op0 = xs[1] if rows[i].get("merge_op_left") else xs[c_op]
            cell_lines(pg, x_op0, xs[c_op + 1], y0, op)
            cell_lines(pg, xs[c_op + 1], xs[c_op + 2], y0, ac)
            cell_lines(pg, xs[-2], xs[-1], y0, st, center=True)
        # 병합칸 글자: 이 쪽에 걸린 몫(칸 높이)만큼 줄을 꺼내 쓴다. 남은 줄은 다음 쪽으로 넘어간다.
        for col, gid, q in ((0, dg, dq), (1, lg, lq)):
            if col == 1 and not city:
                continue
            j = 0
            while j < len(ss):
                g = gid[ss[j][0]]
                k = j
                while k + 1 < len(ss) and gid[ss[k + 1][0]] == g:
                    k += 1
                if g is not None:
                    y0, y1 = ss[j][1], ss[k][2]
                    cap = math.floor((y1 - y0 - 2 * PADY) / LH)
                    take, q[g] = q[g][:cap], q[g][cap:]
                    cell_lines(pg, xs[col], xs[col + 1], y0, take, center=True)
                j = k + 1


# ───────────────────────────── 조립 ─────────────────────────────
def build_pages():
    pages = []
    pg = Page(1)
    pages.append(pg)
    pg.text(40, 30, DATA["title"], 12)
    pg.text(40, 48, DATA["date_line"], 9)
    pg.text(40, TOP - 30 + 20, "1. 총괄표", 11)
    draw_summary(pg, TOP + 20)
    ranges = {}
    for grp in DATA["groups"]:
        s = len(pages) + 1
        layout_group(pages, grp)
        ranges[grp["name"]] = [s, len(pages)]
    return pages, ranges


def paint(page, pg, dx):
    sh = page.new_shape()
    dl, gap = L["dash_len"], L["dash_gap"]
    for x0, y0, x1, y1, dotted in pg.lines:
        if dotted:                                   # 한컴식 점선: 짧은 조각을 따로따로 긋는다
            x = x0
            while x < x1:
                sh.draw_line((dx + x, y0), (dx + min(x + dl, x1), y0))
                x += dl + gap
        else:
            sh.draw_line((dx + x0, y0), (dx + x1, y1))
    sh.finish(color=(0, 0, 0), width=0.4)
    sh.commit()
    for x, y, s, fs in pg.texts:
        page.insert_text((dx + x, y), s, fontname="K", fontsize=fs)
    num = f"- {pg.no} -"
    page.insert_text((dx + (PW - tlen(num, 8)) / 2, PH - 30), num, fontname="K", fontsize=8)


def write_pdf(pages, out):
    doc = fitz.open()
    two = L.get("two_up", False)
    step = 2 if two else 1
    for i in range(0, len(pages), step):
        page = doc.new_page(width=PW * (2 if two else 1), height=PH)
        page.insert_font(fontname="K", fontbuffer=FONT.buffer)
        paint(page, pages[i], 0)
        if two and i + 1 < len(pages):
            paint(page, pages[i + 1], PW)
    doc.subset_fonts()
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out, garbage=4, deflate=True)
    return doc.page_count


def write_evidence(d, out):
    doc = fitz.open()
    page = doc.new_page(width=PW, height=PH)
    page.insert_font(fontname="K", fontbuffer=FONT.buffer)
    y = 80
    page.insert_text(((PW - tlen(d["sender"], 18)) / 2, y), d["sender"], fontname="K", fontsize=18)
    y += 50
    for s in (f"수신  예시 산업단지 사업시행자", "(경유)", f"제목  {d['subject']}"):
        page.insert_text((60, y), s, fontname="K", fontsize=10.5)
        y += 22
    y += 10
    body = ["1. 귀 기관의 협의 요청과 관련입니다.",
            "2. 위 사업에 대한 우리 기관의 검토 의견을 다음과 같이 회신합니다."] + ["  " + x for x in d["items"]] + ["", "끝."]
    for para in body:
        for ln in wrap(para, PW - 120, 10.5) or [""]:
            page.insert_text((60, y), ln, fontname="K", fontsize=10.5)
            y += 17
    y += 30
    page.insert_text((60, y), f"{d['sender']}장", fontname="K", fontsize=14)
    page.insert_text((60, PH - 60), f"시행  {d['doc_no']} ({d['date']})", fontname="K", fontsize=9)
    doc.subset_fonts()
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out, garbage=4, deflate=True)


def main():
    pages, ranges = build_pages()
    out = cfg.path("source_pdf")
    n = write_pdf(pages, out)
    print(f"예시 PDF: {out.relative_to(cfg.ROOT)}  (장 {n} · 논리쪽 {len(pages)})")
    print("기관군별 논리쪽:", ranges)
    want = {g["name"]: g["pages"] for g in cfg.GROUPS}
    if want != ranges:
        print("  ⚠ config/project.json groups[].pages와 다름. 설정을 위 값으로 고칠 것:", want)
    ev = cfg.path("evidence_dir")
    for d in DATA["evidence_docs"]:
        write_evidence(d, ev / d["file"])
        print(f"가상 회신 공문: {(ev / d['file']).relative_to(cfg.ROOT)}")


if __name__ == "__main__":
    main()
