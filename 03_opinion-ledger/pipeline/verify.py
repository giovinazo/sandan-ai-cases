# -*- coding: utf-8 -*-
"""검증: 원본 총괄표 vs 대장 전수 대조 + 독립 집계 → 검증리포트(md).

① 총괄표 대조  : 부서별로 총괄표 수치와 대장(구분 '본협의') 건수·상태 분포를 맞춰 본다.
② 독립 집계    : 레코드 조립 로직을 거치지 않고, 상세표 쪽마다 '반영여부' 칸 글자만 직접 세어
                 대장의 반영·부분반영·미반영 건수와 맞춰 본다(조립 오류가 있으면 여기서 어긋난다).
불일치가 있으면 종료 코드 1을 돌려 run_all.py가 멈춘다.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

import cfg
from build_records import page_bands
from pages import logical_pages
from parse_summary import parse as parse_summary, totals

STATS = ("반영", "부분반영", "미반영", "의견없음", "미회신")
ORG_FIX = cfg.N.get("org_fix", {})


def flat(s):
    return re.sub(r"\s+", "", s or "")


def key(org, dept):
    return (flat(ORG_FIX.get(flat(org), flat(org))), flat(dept))


def load_records():
    return json.load(open(cfg.work("records.json"), encoding="utf-8"))


def build():
    """부서별 대조표 행 목록(대시보드 엑셀 검증 시트에도 쓴다)"""
    summ = parse_summary()
    recs = [r for r in load_records() if r["구분"] == "본협의"]
    want = {}
    for s in summ:
        want[key(s["관계기관"], s["소관부서"])] = s
    got = defaultdict(lambda: defaultdict(int))
    meta = {}
    for r in recs:
        k = key(r["관계기관"], r["소관부서"])
        got[k][r["반영여부"]] += 1
        meta.setdefault(k, r)
    order = {g: i for i, g in enumerate(cfg.GROUP_NAMES)}
    rows = []
    for k in sorted(set(want) | set(got),
                    key=lambda k: (order.get((want.get(k) or meta.get(k, {})).get("기관군"), 99), k)):
        w = want.get(k)
        g = got.get(k, {})
        m = meta.get(k, {})
        exp = [w[s] for s in STATS] if w else [None] * 5
        act = [g.get(s, 0) for s in STATS] + [g.get("미기재", 0)]
        et = sum(exp) if w else None
        at = sum(act)
        st_ok = w is not None and exp == act[:5] and act[5] == 0
        rows.append(dict(
            기관군=(w or m).get("기관군", ""),
            관계기관=(w["관계기관"] if w else m.get("관계기관", "")),
            소관부서=(w["소관부서"] if w else m.get("소관부서", "")),
            총괄표계=et, 대장계=at, 차이=(at - et if et is not None else None),
            **{f"총괄_{s}": (exp[i] if w else None) for i, s in enumerate(STATS)},
            **{f"대장_{s}": act[i] for i, s in enumerate(STATS)},
            대장_미기재=act[5],
            일치=("○" if et == at else "✗"),
            상태일치=("○" if st_ok else "✗"),
            비고=(w["비고"] if w else "총괄표에 없음")))
    return rows


def independent_tally():
    """상세표 '반영여부' 칸 글자만 직접 센다(레코드 조립과 무관)."""
    pages = logical_pages(str(cfg.path("source_pdf")))
    c = Counter()
    for g in cfg.GROUPS:
        for pi in range(g["pages"][0] - 1, g["pages"][1]):
            bands, _ = page_bands(pages[pi])
            for i, b in enumerate(bands or []):
                s = flat(b["st"])
                if i == 0 and s == "반영여부":
                    continue
                for k in ("부분반영", "미반영", "반영"):
                    if k in s:
                        c[k] += 1
                        break
    return c


def main():
    rows = build()
    recs = load_records()
    summ = parse_summary()
    bad = [r for r in rows if r["일치"] != "○"]
    bad_st = [r for r in rows if r["상태일치"] != "○"]
    s_tot = totals(summ)
    bon = [r for r in recs if r["구분"] == "본협의"]
    l_tot = Counter(r["반영여부"] for r in bon)
    ind = independent_tally()
    led = Counter(r["반영여부"] for r in recs)
    ind_bad = [k for k in ("반영", "부분반영", "미반영") if ind[k] != led[k]]

    print(f"부서 {len(rows)}개 / 건수 불일치 {len(bad)}개 / 상태 분포 불일치 {len(bad_st)}개")
    for r in bad + [x for x in bad_st if x not in bad]:
        print(f"  ✗ {r['기관군']:5s} {r['관계기관']:10s} {r['소관부서']:14s} 총괄{r['총괄표계']} 대장{r['대장계']}")
    print("총괄표 합계", s_tot)
    print("대장 합계  ", {s: l_tot.get(s, 0) for s in STATS}, "미기재", l_tot.get("미기재", 0))
    print("독립 집계(반영여부 칸 직접)", dict(ind), "↔ 대장 전체", {k: led[k] for k in ("반영", "부분반영", "미반영")},
          "불일치" if ind_bad else "일치")

    P = cfg.C["project"]
    md = [f"# 협의대장 검증리포트 ({P['name']} · {P['edition']})", "",
          f"생성 {datetime.now():%Y-%m-%d %H:%M} · 원본 `{cfg.C['paths']['source_pdf']}`", "",
          "## 1. 총괄표 전수 대조", "",
          f"- 총괄표 부서 {len(summ)}개, 대장 부서 {len(rows)}개",
          f"- **건수 불일치 {len(bad)}개 · 상태 분포 불일치 {len(bad_st)}개**", "",
          "| 항목 | 총괄표 | 대장(본협의) |", "|---|--:|--:|",
          f"| 검토의견 계 | {s_tot['계']} | {sum(l_tot[s] for s in STATS if s != '미회신') + l_tot.get('미기재', 0)} |"]
    for s in STATS:
        md.append(f"| {s} | {s_tot[s]} | {l_tot.get(s, 0)} |")
    md += ["", "※ '계'는 검토의견 건수, '미회신'은 회신하지 않은 부서 수(단위가 다르다). "
           "재협의(2차 이상)와 총괄표 미집계 행은 총괄표 대조에서 뺀다.", "",
           "| 기관군 | 관계기관 | 소관부서 | 총괄표 | 대장 | 건수 | 상태 |", "|---|---|---|--:|--:|:-:|:-:|"]
    for r in rows:
        md.append(f"| {r['기관군']} | {r['관계기관']} | {r['소관부서']} | {r['총괄표계']} | {r['대장계']} "
                  f"| {r['일치']} | {r['상태일치']} |")
    md += ["", "## 2. 독립 집계(반영여부 칸 글자 직접 세기)", "",
           "레코드 조립(밴드 병합·부서 배정)을 거치지 않고 상세표 쪽마다 반영여부 칸 글자만 센 값과 "
           "대장 전체(본협의+재협의+미집계) 값을 맞춘다.", "",
           "| 상태 | 칸 직접 집계 | 대장 |", "|---|--:|--:|"]
    for k in ("반영", "부분반영", "미반영"):
        md.append(f"| {k} | {ind[k]} | {led[k]} |")
    md += ["", f"결과: **{'불일치 ' + ', '.join(ind_bad) if ind_bad else '전 항목 일치'}**", "",
           "## 3. 대장 구성", "",
           f"- 대장 {len(recs)}행 = 본협의 {len(bon)} + 재협의 {sum(1 for r in recs if r['구분'] == '재협의')}"
           f" + 총괄표 미집계 {sum(1 for r in recs if r['구분'] == '총괄표 미집계')}",
           "- 총괄표 미집계: 원본 상세표에는 있으나 총괄표가 세지 않은 행. 행은 남기고 집계에서 뺀다.", ""]
    for r in recs:
        if r["구분"] == "총괄표 미집계":
            md.append(f"  - 연번 {r['연번']} {r['관계기관']} {r['소관부서']} · {r['반영여부']} · "
                      f"{flat(r['협의의견'])[:30]}…")
    open(cfg.out("verify_report"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("저장:", cfg.out("verify_report").relative_to(cfg.ROOT))
    return 1 if (bad or bad_st or ind_bad) else 0


if __name__ == "__main__":
    sys.exit(main())
