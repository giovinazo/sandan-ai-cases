# -*- coding: utf-8 -*-
"""상세 협의의견 표(설정 groups[].pages 쪽) → 레코드 초안(raw_records.json).

한 쪽의 표를 괘선으로 복원한 뒤, 맨 끝 열(반영여부) 칸 단위를 '밴드'로 잡고
밴드를 이어 붙이거나 끊어 협의의견 한 건씩으로 만든다.

열 구성
  · 4열(central·province·agency): 첫 칸 | 협의의견 | 조치계획 | 반영여부
  · 5열(city)                    : 부서(+접수문서번호) | 근거법령 | 검토의견 | 조치계획 | 반영여부
"""
import json
import re

import cfg
import grid
from pages import logical_pages

PDF = str(cfg.path("source_pdf"))
SECTIONS = [(g["pages"][0], g["pages"][1], g["name"]) for g in cfg.GROUPS]
BULLET = ("○", "◦")
MARK = re.compile(r"^\s*\[\s*([^\]]{2,40})\s*\]")


def starts_new(op, ac, st):
    """새 레코드 시작 판정.

    반영여부 칸에 값이 찍혔거나(= 한 건의 종결), 협의의견·조치계획이 ○로 시작하면 새 건.
    '-'·'*'로 시작하는 줄은 앞 건의 하위 항목이므로 이어 붙인다.
    '[붙임…]'은 부서 표시가 아니라 앞 건의 연속.
    """
    o, a = op.lstrip(), ac.lstrip()
    if MARK.match(o) and not o.startswith("[붙임"):
        return True
    if st.strip():
        return True
    return o.startswith(BULLET) or a.startswith(BULLET)


def ns(s):
    return re.sub(r"[ \t]{2,}", " ", (s or "")).strip()


def flat(s):
    return re.sub(r"\s+", "", s or "")


def page_bands(pg):
    """쪽 → [dict(dept, law, op, ac, st, law_o)]  반영여부 칸 단위 = 밴드"""
    g = grid.Grid(pg)
    if not g.ok or g.nc < 4:
        return None, 0
    nc = g.nc
    last = nc - 1
    bands = []
    r = 0
    while r < g.nr:
        o = g.origin[r][last]
        r0 = o[0]
        r1 = r0
        while r1 + 1 < g.nr and g.origin[r1 + 1][last] == o:
            r1 += 1
        if r0 == r:
            bands.append((r0, r1))
        r = r1 + 1
    out = []
    op_c = 1 if nc == 4 else 2
    ac_c = op_c + 1
    for r0, r1 in bands:
        y0, y1 = g.ys[r0], g.ys[r1 + 1]
        # 근거법령 칸이 없는 행은 협의의견 칸이 왼쪽 칸과 병합된다.
        # 고정 열 번호로 읽으면 줄마다 앞 4~5글자가 통째로 잘리므로 병합 원점 열부터 읽는다.
        # (잘려도 문장이 그럴듯하게 남아 눈에 잘 띄지 않는 함정)
        c_lo = op_c
        o = g.origin[r0][op_c]
        if 1 <= o[1] < op_c:
            c_lo = o[1]
        op = ns(grid.cell_text(pg, g.xs[c_lo], g.xs[op_c + 1], y0, y1, chars=g.chars))
        ac = ns(grid.cell_text(pg, g.xs[ac_c], g.xs[ac_c + 1], y0, y1, chars=g.chars))
        st = ns(g.cells[r0][last] or "")
        dept = ns(g.cells[r0][0] or "")
        law = ns(g.cells[r0][1] or "") if nc >= 5 and c_lo == op_c else ""
        law_o = g.origin[r0][1][0] if nc >= 5 else -1
        out.append(dict(dept=dept, law=law, op=op, ac=ac, st=st, law_o=law_o))
    return out, nc


LAW_END = ("법", "법률", "령", "규칙", "조례", "지침", "기준", ")", "결과", "평가", "사항")


def known_city_depts():
    """총괄표의 city 역할 부서명(쪽 경계 부서명 조각 판정용)"""
    from parse_summary import parse as parse_summary
    ks = set()
    for s in parse_summary():
        if cfg.ROLE.get(s["기관군"]) == "city":
            ks.add(flat(s["소관부서"]))
            ks.add(flat(s["관계기관"] + s["소관부서"]))
    return ks


KNOWN_CITY = known_city_depts()


def join_law_across_pages(bands):
    """쪽에 걸친 근거법령 병합칸 이어 붙이기.

    근거법령 칸은 여러 행을 세로로 합친 병합칸이라 쪽이 바뀌면 글자가 앞 쪽에만 남거나
    (다음 쪽은 빈칸), 줄 단위로 두 쪽에 갈린다('주차장법 및' / '교통영향평가').
    어디서 갈리는지는 판마다 다르다(쪽 안 줄 나눔이 한 줄만 어긋나도 바뀐다).
    다음 쪽 첫 밴드의 부서칸이 비었거나 부서명 조각이면(= 같은 부서가 이어짐)
      · 다음 쪽 법령칸이 빈칸이면 앞 쪽 글을 물려주고
      · 둘 다 글이 있고 앞 쪽 글이 법령명·괄호로 끝나지 않으면(조각) 둘을 이어 양쪽에 준다.
    """
    by_page = {}
    for b in bands:
        by_page.setdefault(b["page"], []).append(b)
    n_inh = n_join = 0
    for pg in sorted(by_page):
        if pg - 1 not in by_page:
            continue
        cur, prev = by_page[pg], by_page[pg - 1]
        f, l = cur[0], prev[-1]
        if not (f["gun"] == l["gun"] and cfg.ROLE.get(f["gun"]) == "city" and f["nc"] == l["nc"] == 5):
            continue
        name = re.split(r"-\d{3,}", flat(f["dept"]))[0]
        if name and name in KNOWN_CITY:
            continue                                   # 새 부서가 시작되는 쪽(부서명이 온전히 찍힘)
        L1, L2 = l["law"], f["law"]
        reg_prev = [x for x in prev if x["law_o"] == l["law_o"]]
        reg_cur = [x for x in cur if x["law_o"] == f["law_o"]]
        if L1 and not L2:
            for x in reg_cur:
                x["law"] = L1
            n_inh += len(reg_cur)
        elif L1 and L2 and flat(L1) != flat(L2) and not flat(L1).endswith(LAW_END):
            merged = (L1.rstrip() + "\n" + L2.lstrip()).strip()
            for x in reg_prev + reg_cur:
                x["law"] = merged
            n_join += 1
            print(f"  쪽 경계 근거법령 조각 병합 p{pg-1}/{pg}: '{flat(L1)[:20]}' + '{flat(L2)[:20]}'")
    print(f"  근거법령 쪽 경계 처리: 물려줌 {n_inh}밴드 / 조각 병합 {n_join}건")
    return bands


def has_mark(b):
    o = b["op"].lstrip()
    return bool(MARK.match(o)) and not o.startswith("[붙임")


def join(a, b):
    a["op"] = (a["op"] + "\n" + b["op"]).strip()
    a["ac"] = (a["ac"] + "\n" + b["ac"]).strip()
    a["st"] = (a["st"] + " " + b["st"]).strip()
    return a


def collect_bands():
    pages = logical_pages(PDF)
    bands = []
    for p0, p1, gun in SECTIONS:
        for pi in range(p0 - 1, p1):
            pg = pages[pi]
            bs, nc = page_bands(pg)
            if bs is None:
                print(f"  !! p{pi+1} 괘선 복원 실패")
                continue
            for i, b in enumerate(bs):
                if i == 0 and ("의견" in flat(b["op"]) and "조치계획" in flat(b["ac"])):
                    continue                                   # 쪽마다 반복되는 머리행
                if not (b["op"] or b["ac"] or b["st"]):
                    continue
                b.update(gun=gun, page=pi + 1, nc=nc)
                bands.append(b)
    return bands


def main():
    bands = join_law_across_pages(collect_bands())

    # 1단계: 협의의견이 비고 반영여부도 없는 칸 = 앞 건의 조치계획이 쪽을 넘어온 것
    recs = []
    for b in bands:
        if recs and recs[-1]["gun"] == b["gun"] and not b["op"] and not b["st"].strip():
            join(recs[-1], b)
        elif recs and recs[-1]["gun"] == b["gun"] and not starts_new(b["op"], b["ac"], b["st"]):
            join(recs[-1], b)
        else:
            recs.append(b)

    # 2단계: 조치계획·반영여부가 모두 빈 칸 = 다음 건에 의견이 이어짐
    #        (부서 표시만 있는 행, 조치계획 없이 의견만 이어지는 행)
    out = []
    hold = None
    for b in recs:
        if hold is not None:
            if hold["gun"] == b["gun"] and not has_mark(b):
                b = join(hold, b)
            else:
                out.append(hold)
            hold = None
        bare = flat(b["op"]) in ("", "○", "-")
        if not b["ac"].strip() and not b["st"].strip() and not bare:
            hold = b
            continue
        out.append(b)
    if hold is not None:
        out.append(hold)
    json.dump(out, open(cfg.work("raw_records.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print("레코드", len(out), dict(Counter(r["gun"] for r in out)))
    return out


if __name__ == "__main__":
    main()
