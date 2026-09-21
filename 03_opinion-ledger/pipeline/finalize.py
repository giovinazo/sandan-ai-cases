# -*- coding: utf-8 -*-
"""norm_records → 대장 레코드 확정(records.json).

  · 반영여부 분류(반영·부분반영·미반영·의견없음·미회신·미기재)
  · 재협의 식별: 부서칸·의견 첫머리의 '(2차협의)' 이상 → 구분 '재협의'
    (재협의가 별도 PDF로 오는 판이면 paths.rehyeobui_pdf를 주고 parse_rehyeobui()로 붙인다.
     본협의 표에 이미 통합된 판에서 별도 PDF를 또 붙이면 그만큼 중복된다)
  · 쟁점유형 자동 태깅(설정 issues)
  · 총괄표 대조: 총괄표가 세지 않은 행은 구분 '총괄표 미집계'로 두어 집계에서 뺀다
  · 수기 비고(annotations.json)를 연번+지문이 맞는 건에만 붙인다
"""
import json
import os
import re
from collections import Counter, defaultdict

import pdfplumber

import cfg
import grid
from normalize import assign, flat, load

ORG_FIX = cfg.N.get("org_fix", {})
ISSUE = [(name, kws) for name, kws in cfg.C["issues"]["types"]]
ISSUE_REPLACE = cfg.C["issues"].get("replace_before_tagging", {})
NONE_WORDS = tuple(cfg.C["classify"]["none_words"])
STATS = ("반영", "부분반영", "미반영", "의견없음", "미회신")


def tag_issue(*parts):
    # 개행만 지운다(PDF 줄바꿈이 단어를 쪼갬). 공백까지 지우면 '산업단지 진출입' → '…지진…'처럼
    # 인접 어절이 붙어 엉뚱한 키워드를 만들어 낸다.
    t = re.sub(r"[\n\r]+", "", " ".join(parts)).lower()
    # 긴 낱말 안의 짧은 키워드 오탐 방지: '매장문화재'의 '화재'가 재난·안전에 잡히지 않도록 치환 후 판정
    for a, b in ISSUE_REPLACE.items():
        t = t.replace(a, b)
    for name, kws in ISSUE:
        if any(k.lower() in t for k in kws):
            return name
    return "기타"


def first_law(op, law):
    if law and flat(law).strip("-\u2013\u2014·"):           # 법령칸이 '-'뿐이면 빈칸으로 본다
        return law
    for x in re.findall(r"[「｢]([^」｣]{2,40})[」｣]", op):
        if x.endswith(("법", "령", "규칙", "조례", "지침", "기준", "특례법", "방침", "법률")):
            return f"｢{x}｣"
    return ""


def classify(st, op, ac=""):
    s = flat(st)
    for k in ("부분반영", "미반영", "의견없음", "반영"):
        if k in s:
            return k
    o = flat(op)
    if not o or o == "○":
        return "미회신"
    if "별도회신" in o or ("별도" in o and "회신" in o):    # '○○로 별도 회신 예정' = 실질 무회신
        return "미회신"
    if any(x in o for x in NONE_WORDS):
        return "의견없음"
    if s.strip("-") == "" and s:
        # 반영여부 칸이 '-'. 조치계획이 '해당없음'류면 실질 의견없음이고,
        # 아니면 작성자가 조치계획·반영여부를 안 채운 미기재다.
        if any(x in flat(ac) for x in NONE_WORDS):
            return "의견없음"
        return "미기재"
    return "미기재"


def parse_rehyeobui():
    """재협의가 별도 PDF로 온 판 전용(설정 paths.rehyeobui_pdf). 표 머리의 기관군 이름으로 구분한다."""
    pdf = cfg.path("rehyeobui_pdf")
    if not pdf:
        return []
    p = pdfplumber.open(str(pdf))
    out = []
    gun = dept = law = ""
    for pi in range(len(p.pages)):
        g = grid.Grid(p.pages[pi])
        if not g.ok:
            continue
        for r in range(g.nr):
            row = [g.cells[r][c] or "" for c in range(g.nc)]
            joined = flat(" ".join(row[:2]))
            if row[0] == row[-1]:                       # 전폭 병합행(소제목)
                for name in cfg.GROUP_NAMES:
                    if name in joined:
                        gun, dept = name, ""
                continue
            if "검토의견" in flat(" ".join(row)) or "협의의견" in flat(" ".join(row)):
                continue
            if g.nc >= 5:
                d, l, op, ac, st = row[0], row[1], row[2], row[3], row[4]
            else:
                d, l, op, ac, st = row[0], "", row[1], row[2], row[3]
            if flat(d):
                dept = flat(d)
            if flat(l) and flat(l) != flat(op):
                law = re.sub(r"\s+", " ", l.replace("\n", " ")).strip()
            if not (flat(op) or flat(ac)):
                continue
            org = cfg.N["city_org"] if cfg.ROLE.get(gun) == "city" else cfg.N.get("rehyeobui_default_org", gun)
            out.append(dict(기관군=gun, 관계기관=org, 소관부서=dept, 팀="", 접수문서번호="", 시행일자="",
                            근거법령=law, 협의의견=op, 조치계획=ac, 반영여부원문=st, 페이지=pi + 1,
                            구분="재협의"))
    return out


def parse_major():
    """주요 협의의견 요약본 PDF(설정 paths.major_pdf, 선택) → 목록"""
    pdf = cfg.path("major_pdf")
    if not pdf:
        return []
    p = pdfplumber.open(str(pdf))
    out = []
    org = ""
    for pi in range(len(p.pages)):
        g = grid.Grid(p.pages[pi])
        if not g.ok or g.nc < 5:
            continue
        for r in range(g.nr):
            row = [g.cells[r][c] or "" for c in range(g.nc)]
            if "조치계획" in flat(" ".join(row)) or "협의의견" in flat(row[2] if len(row) > 2 else ""):
                continue
            if flat(row[0]):
                org = flat(row[0])
            dept, op, ac, bigo = flat(row[1]), row[2], row[3], flat(row[4])
            if not (flat(op) or flat(ac)):
                continue
            out.append(dict(관계기관=org, 소관부서=dept, 협의의견=op, 조치계획=ac, 비고=bigo, 페이지=pi + 1))
    return out


def finish(recs, 구분="본협의"):
    out = []
    for r in recs:
        st_raw = re.sub(r"\s+", " ", r["반영여부원문"]).strip()
        org = ORG_FIX.get(r["관계기관"], r["관계기관"])
        stat = classify(st_raw, r["협의의견"], r["조치계획"])
        att = re.findall(r"붙임\s*([0-9]{1,2})", st_raw)
        cha = str(r.get("협의차수", "") or "")
        is_re = (cha.isdigit() and int(cha) >= 2) or r.get("구분") == "재협의"
        gubun = "재협의" if is_re else r.get("구분", 구분)
        jae = "Y" if is_re or "재협의" in flat(st_raw) else ""
        bigo = []
        if is_re and cha:
            bigo.append(f"{cha}차협의(본협의표 통합)")
        if att:
            bigo.append("근거첨부:붙임" + ",".join(att))
        if "재협의" in flat(st_raw):
            bigo.append("재협의 진행중")
        if stat == "미기재":
            bigo.append("반영여부 미기재-검수")
        if stat == "미회신":
            bigo.append("무응답/미회신")
        out.append(dict(
            기관군=r["기관군"], 관계기관=org, 소관부서=r["소관부서"], 팀=r.get("팀", ""),
            구분=gubun, 협의차수=cha,
            접수문서번호=r.get("접수문서번호", ""), 시행일자=r.get("시행일자", ""),
            근거법령=first_law(r["협의의견"], r["근거법령"]),
            협의의견=r["협의의견"], 조치계획=r["조치계획"],
            반영여부=stat, 반영여부원문=st_raw, 재협의=jae,
            쟁점유형=tag_issue(r["협의의견"], r["조치계획"], r["소관부서"], r["근거법령"]),
            비고=" / ".join(bigo), 출처페이지=r["페이지"]))
    return out


def key(o, d):
    return (flat(ORG_FIX.get(flat(o), flat(o))), flat(d))


def flag_vs_summary(main):
    """원본 총괄표(부서별 행)와 대장을 대조해 차이 나는 건에 비고를 남긴다."""
    from parse_summary import parse as parse_summary
    want = {key(s["관계기관"], s["소관부서"]): s for s in parse_summary()}
    grp = defaultdict(list)
    for r in main:
        if r["구분"] != "본협의":          # 총괄표는 재협의 통합분을 집계하지 않는다
            continue
        grp[key(r["관계기관"], r["소관부서"])].append(r)
    n_over = n_stat = 0
    for k, rows in grp.items():
        w = want.get(k)
        if not w:
            continue
        exp_tot = sum(w[s] for s in STATS)
        # ① 총괄표가 세지 않은 행: 반영여부 칸이 '-'인 안내성 행부터 표시
        over = len(rows) - exp_tot
        if over > 0:
            cand = [r for r in rows if r["반영여부원문"] == "-"] or rows
            for r in cand[-over:]:
                r["비고"] = " / ".join(filter(None, [r["비고"], "원본 총괄표 미집계"]))
                r["구분"] = "총괄표 미집계"   # 행은 남기되 본협의 집계에서 뺀다(집계는 원본 총괄표에 맞춘다)
                n_over += 1
        # ② 건수는 같은데 상태 분포가 다른 경우
        got = {s: sum(1 for r in rows if r["반영여부"] == s) for s in STATS}
        if over <= 0 and got != {s: w[s] for s in STATS}:
            diff = [s for s in STATS if got[s] != w[s]]
            for r in rows:
                if r["반영여부"] in diff and w[r["반영여부"]] < got[r["반영여부"]]:
                    alt = [s for s in diff if w[s] > got[s]]
                    r["비고"] = " / ".join(filter(None, [
                        r["비고"], f"원본 총괄표는 이 건을 {alt[0] if alt else '다른 상태'}으로 집계(불일치)"]))
                    n_stat += 1
    print(f"  총괄표 미집계 표시 {n_over}건 / 상태 불일치 표시 {n_stat}건")
    return main


def apply_annotations(recs):
    """annotations.json의 수기 비고를 연번+지문이 맞는 건에 덧붙인다. 지문이 어긋나면 멈춘다."""
    path = cfg.path("annotations")
    if not path or not os.path.exists(path):
        return recs
    ann = json.load(open(path, encoding="utf-8")).get("항목", [])
    by = {r["연번"]: r for r in recs}
    for a in ann:
        r = by.get(a["연번"])
        fp = a["지문"]
        if not r or r["소관부서"] != fp["소관부서"] or flat(r["협의의견"])[:20] != fp["협의의견앞20자"]:
            raise SystemExit(f"annotations.json 연번 {a['연번']} 지문 불일치. 판이 바뀌었으면 연번을 재매핑할 것")
        r["비고"] = " / ".join(filter(None, [r["비고"], a["비고추가"]]))
    print(f"  수기 비고 적용 {len(ann)}건")
    return recs


if __name__ == "__main__":
    base = assign(load())
    extra = parse_rehyeobui()                       # 별도 재협의 PDF가 있는 판만
    recs = flag_vs_summary(finish(base + extra))
    for i, r in enumerate(recs, 1):
        r["연번"] = i
    recs = apply_annotations(recs)
    json.dump(recs, open(cfg.work("records.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    major = parse_major()
    json.dump(major, open(cfg.work("major.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bon = [r for r in recs if r["구분"] == "본협의"]
    jae = [r for r in recs if r["구분"] == "재협의"]
    etc = [r for r in recs if r["구분"] == "총괄표 미집계"]
    print(f"대장 {len(recs)}행 = 본협의 {len(bon)} + 재협의 {len(jae)} + 총괄표 미집계 {len(etc)}")
    print("본협의", dict(Counter(r["반영여부"] for r in bon)))
    print("재협의", dict(Counter(r["반영여부"] for r in jae)))
    print("주요 협의의견", len(major))
    print("쟁점유형", Counter(r["쟁점유형"] for r in recs).most_common())
