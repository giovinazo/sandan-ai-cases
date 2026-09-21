# -*- coding: utf-8 -*-
"""총괄표(설정 summary.pages 쪽) → 기관군·관계기관·소관부서별 집계. 대장 검증의 기준값이다.

총괄표 열 구성(10열): 구분 | 관계기관 | 협의부서 | 계 | 반영 | 부분반영 | 미반영 | 의견없음 | 미회신 | 비고
  · 구분·관계기관 칸은 세로 병합칸이다(병합 원점의 글자를 아래 행이 물려받는다)
  · 소계·계 행은 건너뛴다
  · '계'는 검토의견 건수, '미회신'은 회신하지 않은 부서 수다(단위가 다르다)
"""
import json
import re

import cfg
import grid
from pages import logical_pages

PDF = str(cfg.path("source_pdf"))
S = cfg.C["summary"]
N = cfg.N
SKIP_DEPT = ("계", "소계", "합계")


def n(s):
    return re.sub(r"\s+", "", s or "")


def num(s):
    s = n(s)
    return int(s) if s.isdigit() else 0              # '-'·공란은 0


def group_of(c0, cur):
    names = list(cfg.GROUP_NAMES) + list(S.get("group_alias", {}))
    for name in sorted(names, key=len, reverse=True):
        if c0.startswith(name):
            return S.get("group_alias", {}).get(name, name)
    return cur


def split_org(gun, sub, dept):
    """총괄표 한 행의 (관계기관, 소관부서) 결정. 기관군 역할(role)마다 적는 방식이 다르다."""
    role = cfg.ROLE.get(gun)
    if role == "central":                            # 관계기관 칸 = 부처 약칭(부서 수)
        base = re.sub(r"\(\d+\)", "", sub)
        return S.get("org_abbr", {}).get(base, base), dept
    if role == "province":                           # 관계기관 칸에 소속기관 표시
        org = N["province_default_org"]
        for kw, o in N.get("province_sub_org_keywords", {}).items():
            if kw in sub:
                org = o
        parents = N.get("province_parent_orgs", [])
        if parents:
            mm = re.match(r"^(" + "|".join(map(re.escape, parents)) + r")\((.+)\)$", dept)
            if mm:
                org, dept = mm.group(1), mm.group(2)
        return org, dept
    if role == "city":                               # 부서칸 앞에 소속기관이 붙어 오는 경우 분리
        for pre in N.get("city_prefix_orgs", []):
            if dept.startswith(pre):
                return pre, dept[len(pre):]
        return N["city_org"], dept
    mm = re.match(N["agency_split_regex"], dept)     # 유관기관: '○○공사 ○○본부' → 기관·부서
    if mm and mm.group(2):
        return mm.group(1), mm.group(2)
    return dept, dept


def parse():
    pages = logical_pages(PDF)
    rows = []
    for pno in S["pages"]:
        g = grid.Grid(pages[pno - 1], vfrac=float(cfg.P.get("summary_col_min_height_frac", 0.05)))
        if not g.ok:
            raise SystemExit(f"총괄표 {pno}쪽 괘선 복원 실패. summary.pages와 쪽 구성을 확인할 것")
        for r in range(g.nr):
            rows.append([g.cells[r][c] or "" for c in range(g.nc)])
    out, gun = [], ""
    for cells in rows:
        if len(cells) < 10:
            continue
        if n(cells[0]) == "구분" or "협의부서" in n(cells[1]) or "협의부서" in n(cells[2]):
            continue                                 # 머리행
        gun = group_of(n(cells[0]), gun)
        sub, dept = n(cells[1]), n(cells[2])
        if sub == dept:                              # 관계기관·부서 칸이 가로로 합쳐진 행
            sub = ""
        if not dept or dept in SKIP_DEPT or "개부서" in dept or "개기관" in dept:
            continue
        note = re.sub(r"\s+", " ", cells[9]).strip()
        # 총괄표에서 두 부서를 한 행에 병기한 경우 등 판별 규칙(설정 summary.row_rules)
        for rule in S.get("row_rules", []):
            if all(x in dept for x in rule["contains"]):
                dept = rule["dept"]
                note = (note + " " + rule.get("note", "")).strip()
        org, dept = split_org(gun, sub, dept)
        out.append(dict(기관군=gun, 관계기관=org, 소관부서=dept or org,
                        계=num(cells[3]), 반영=num(cells[4]), 부분반영=num(cells[5]),
                        미반영=num(cells[6]), 의견없음=num(cells[7]), 미회신=num(cells[8]),
                        비고=note))
    return out


def totals(recs):
    return {k: sum(r[k] for r in recs) for k in ("계", "반영", "부분반영", "미반영", "의견없음", "미회신")}


if __name__ == "__main__":
    recs = parse()
    json.dump(recs, open(cfg.work("summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(f"총괄표 부서 {len(recs)}개 · 기관군 {dict(Counter(r['기관군'] for r in recs))}")
    print("합계", totals(recs))
    for r in recs:
        print(f"  {r['기관군']:5s}|{r['관계기관']:10s}|{r['소관부서']:14s}|"
              f"계{r['계']:3d} 반{r['반영']:3d} 부{r['부분반영']:2d} 미{r['미반영']:2d} "
              f"없{r['의견없음']:3d} 회{r['미회신']}|{r['비고']}")
