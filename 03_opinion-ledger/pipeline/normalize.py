# -*- coding: utf-8 -*-
"""raw_records → 관계기관·소관부서 배정(norm_records.json) + 총괄표 건수 대조.

기관군 역할(role)마다 부서를 적는 방식이 다르다.
  · central : 첫 칸 = 부처, 협의의견 첫머리 '[부서]' = 소관부서
  · province: 첫 칸 = 과(또는 '소속기관(과)'), '[팀]' = 팀
  · city    : 첫 칸 = 부서 + 접수문서번호 '도로과-10234(2026.01.10.)', 근거법령 칸이 따로 있다
  · agency  : 첫 칸 = 기관(또는 '기관(본부)'), '[분야]' = 팀
재협의가 본협의 표에 섞여 오면 부서칸 또는 협의의견 첫머리에 '(2차협의)'가 붙는다.
"""
import json
import re
from collections import defaultdict

import cfg
from parse_summary import parse as parse_summary

N = cfg.N
MARK = re.compile(r"^\s*\[\s*([^\]]{2,40})\s*\]\s*", re.S)
CHA = re.compile(r"[(（]\s*([0-9]+)\s*차\s*협의\s*[)）]")
DOC = re.compile(r"([가-힣A-Za-z]+)\s*-\s*(\d{3,})\s*[\(（]?\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})")
# 쪽 넘김으로 부서명과 잘려 병합칸 뒷조각만 남은 번호: '-4401(2026.01.13.)'
FRAG = re.compile("^[-\u2010\u2013]?" r"\s*(\d{3,6})\s*[\(（]\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})")
ALIAS = N.get("dept_alias", {})
ORGALIAS = N.get("org_alias", {})
PROVINCE_PARENTS = set(N.get("province_parent_orgs", []))
CITY_PREFIX = N.get("city_prefix_orgs", [])
AGENCY_RE = re.compile(N["agency_split_regex"])


def flat(s):
    return re.sub(r"\s+", "", s or "")


def split_doc(v):
    """'환경과-7781(2026.01.08)' → ('환경과', '환경과-7781', '2026.01.08')  접수공문 분리"""
    v = flat(v)
    docs = [(f"{m.group(1)}-{m.group(2)}", f"{m.group(3)}.{int(m.group(4)):02d}.{int(m.group(5)):02d}")
            for m in DOC.finditer(v)]
    name = re.split(r"-\d{3,}", v)[0].strip()
    name = CHA.sub("", name)
    return name, " ; ".join(d[0] for d in docs), " ; ".join(d[1] for d in docs)


def load():
    return json.load(open(cfg.work("raw_records.json"), encoding="utf-8"))


def known_city_depts():
    ks = set()
    for s in parse_summary():
        if cfg.ROLE.get(s["기관군"]) == "city":
            ks.add(flat(s["소관부서"]))
            ks.add(flat(s["관계기관"] + s["소관부서"]))
    return ks


KNOWN_CITY = known_city_depts()      # 총괄표의 city 부서명(쪽 경계 조각 병합 판정용)


def assign(recs):
    out = []
    dept = team = ""
    docnum = docdate = ""
    prev_gun = None
    pending = None
    org = sub_org = cha = ""
    last_col0 = ""
    for r in recs:
        role = cfg.ROLE.get(r["gun"])
        if r["gun"] != prev_gun:
            dept = team = docnum = docdate = ""
            org = sub_org = cha = ""
            prev_gun = r["gun"]
        op = r["op"]
        col0 = flat(r["dept"])
        if col0 and col0 != last_col0:
            if role in ("province", "agency"):
                team = ""                        # 첫 칸(기관·과)이 바뀌면 팀 표시를 물려주지 않는다
            last_col0 = col0
        if col0:                                 # 부서칸이 새로 찍힌 행에서만 차수를 갱신
            m_ch = CHA.search(col0)
            cha = m_ch.group(1) if m_ch else ""
        if col0 and role == "city":
            col0, dn, dd = split_doc(col0)
            # 부서칸 병합칸이 쪽에 걸려 부서명 자체가 두 쪽으로 갈린 경우('교통정' / '책과-4401…').
            # 앞 조각과 이어 붙여 총괄표 부서명이 되면 한 부서로 합치고, 앞 조각으로 등재된 건도 고친다.
            if col0 and col0 not in KNOWN_CITY and dept:
                full = ""
                if (dept + col0) in KNOWN_CITY:              # 앞 쪽 조각 + 이번 조각
                    full = dept + col0
                    for prev in out:                        # 앞 조각으로 등재된 건을 소급 수정
                        if prev["기관군"] == r["gun"] and prev["소관부서"] == dept:
                            prev["소관부서"] = full
                            if dn and not prev["접수문서번호"]:
                                prev["접수문서번호"], prev["시행일자"] = full + dn[len(col0):], dd
                    print(f"  쪽 경계 부서명 조각 병합: '{dept}' + '{col0}' → '{full}'")
                elif dept in KNOWN_CITY and dept.endswith(col0):   # 같은 쪽의 뒤 행(병합칸 반복)
                    full = dept
                if full:
                    if dn and dn.startswith(col0 + "-"):
                        dn = full + dn[len(col0):]          # '책과-4401' → '교통정책과-4401'
                    col0 = full
            if dn:
                docnum, docdate = dn, dd
            else:
                frag = FRAG.match(flat(r["dept"]))
                if frag and dept:
                    # 병합칸이 쪽에 걸려 번호 조각만 남은 행: 현재 부서의 번호로 복원
                    docnum = f"{dept}-{frag.group(1)}"
                    docdate = f"{frag.group(2)}.{int(frag.group(3)):02d}.{int(frag.group(4)):02d}"
                elif re.match(r"^[가-힣]", col0):
                    # 번호 없이 새 부서칸이 시작되면 직전 부서 번호를 이월하지 않는다.
                    # (이월하면 뒤 부서 수십 건에 앞 부서 문서번호가 조용히 박힌다)
                    docnum = docdate = ""
        col0 = ALIAS.get(col0, col0)
        par = re.match(r"^(.+?)[\(（](.+)[\)）]$", col0) if col0 else None
        m = MARK.match(op)
        newmark = None
        if m:
            newmark = m.group(1).strip()
            op = MARK.sub("", op, count=1).strip()
        if newmark:
            newmark = ALIAS.get(flat(newmark), newmark)
            cha = ""                             # 부서 표시가 새로 찍히면 차수도 초기화
        m_ch = CHA.match(op.lstrip())            # central은 '[부서] (2차협의)' 꼴로 표시 뒤에 붙는다
        if m_ch:
            cha = m_ch.group(1)
            op = CHA.sub("", op.lstrip(), count=1).strip()
        if role == "central":
            if col0:
                org = ORGALIAS.get(col0, col0)
            if newmark:
                dept = newmark
        elif role == "province":
            if col0:
                # 괄호 앞이 소속기관인 경우만 분리('○○과(○○팀)'처럼 괄호가 부서명 일부인 경우는 그대로)
                if par and par.group(1) in PROVINCE_PARENTS:
                    org, dept = par.group(1), par.group(2)
                else:
                    org, dept = N["province_default_org"], col0
            if newmark:
                team = newmark
        elif role == "agency":
            if col0:
                if par:
                    org, dept = par.group(1), par.group(2)
                else:
                    mm = AGENCY_RE.match(col0)
                    org, dept = (mm.group(1), mm.group(2) or mm.group(1)) if mm else (col0, col0)
            if newmark:
                team = newmark
        else:                                    # city
            if col0 and re.match(r"^[가-힣]", col0):
                dept, sub_org = col0, N["city_org"]
                for pre in CITY_PREFIX:
                    if dept.startswith(pre):     # 부서칸에 기관명이 붙어 오는 경우 분리
                        sub_org, dept = pre, dept[len(pre):]
            org = sub_org or N["city_org"]
        if op.strip() in ("○", "-", ""):
            op = op.strip() if op.strip() == "-" else ""
        ac = r["ac"]
        if ac.strip() == "○":
            ac = ""
        cur = dict(기관군=r["gun"], 관계기관=org, 소관부서=(dept or org), 팀=team,
                   협의차수=cha, 접수문서번호=docnum, 시행일자=docdate,
                   근거법령=r["law"], 협의의견=op, 조치계획=ac, 반영여부원문=r["st"],
                   페이지=r["page"])
        if pending is not None and newmark:
            out.append(pending)                  # 무응답 부서(표시만 있는 행) 단독 등재
            pending = None
        if pending is not None:
            # 부서 표시만 있던 행 → 다음 실질 행에 흡수
            cur["협의의견"] = (pending["협의의견"] + "\n" + cur["협의의견"]).strip()
            cur["조치계획"] = (pending["조치계획"] + "\n" + cur["조치계획"]).strip()
            cur["반영여부원문"] = (pending["반영여부원문"] + " " + cur["반영여부원문"]).strip()
            cur["페이지"] = pending["페이지"]
            pending = None
        if not (cur["협의의견"] or cur["조치계획"] or cur["반영여부원문"].strip("-")):
            if newmark or not out:
                pending = cur
                continue
        out.append(cur)
    if pending:
        out.append(pending)
    return out


def reconcile(recs):
    """총괄표 부서별 (계 + 미회신)과 파싱 건수 대조(재협의·미집계 행 포함이라 참고용)"""
    want = {(s["기관군"], flat(s["소관부서"])): s for s in parse_summary()}
    got = defaultdict(int)
    for r in recs:
        got[(r["기관군"], flat(r["소관부서"]))] += 1
    bad = 0
    for k in sorted(set(want) | set(got)):
        w = want.get(k)
        exp = (w["계"] + w["미회신"]) if w else None
        g = got.get(k, 0)
        if exp != g:
            bad += 1
            print(f"  · {k[0]:5s} {k[1]:20s} 총괄표{exp if exp is not None else '-':>4} vs 파싱{g:>4}")
    print(f"부서 {len(set(want) | set(got))}개 중 건수 차이 {bad}개(재협의·총괄표 미집계 행은 finalize에서 가른다)")
    return bad


if __name__ == "__main__":
    recs = assign(load())
    print("정규화 레코드", len(recs))
    json.dump(recs, open(cfg.work("norm_records.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    reconcile(recs)
