#!/usr/bin/env python3
"""
관계기관 협의의견 HTML 대시보드 빌더

  output/<대장 엑셀>  →  output/<대시보드 HTML>   (파일명은 config/project.json output_names)

설계 : 통합 1페이지(KPI → 차트 → 전건 검색·필터 → 상세 패널 → 기관·부서별 현황)
디자인: 다크 기본 + 라이트 토글(우상단 버튼·localStorage 기억, 인쇄는 항상 라이트)
       셸은 스트리밍 앱 계열(좌측 고정 네비 · 상단 검색 · 하단 현재 건 바), 색·타이포는
       IBM Carbon 토큰 유지(IBM Plex Sans KR, 액센트 다크 #4589ff / 라이트 #0f62fe)
폰트 : 실제 사용 문자만 서브셋해 base64 임베드 → 파일 하나로 오프라인 동작(공유 가능)
실행 : python3 html_dashboard/build_html.py [--out 경로] [--no-fonts]
글꼴 : html_dashboard/fonts/에 IBM Plex Sans KR woff2(SIL OFL)를 넣으면 서브셋해 심는다.
       없으면 시스템 글꼴로 보인다(기능 차이 없음).

주의: 산출 HTML을 직접 고치지 말 것(재빌드 시 덮어씀). 내용은 엑셀, 서식은 이 파일에서 수정.
"""
import base64, html, json, os, re, sys
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import cfg  # noqa: E402

VERSION = "v1"          # 화면 판본 · 문서 제목에 붙는다

PJ = cfg.C["project"]
SRC = cfg.out("ledger")
OUT = cfg.out("html")
FONTS = Path(__file__).resolve().parent / "fonts"   # 빌더 자립(다른 폴더 참조 안 함)
WEIGHTS = {400: "IBMPlexSansKR-Regular.woff2", 500: "IBMPlexSansKR-Medium.woff2",
           600: "IBMPlexSansKR-SemiBold.woff2", 700: "IBMPlexSansKR-Bold.woff2"}

BASE_DATE = PJ["base_date"]   # 제출본 기준일 · 판을 새로 받기 전까지 고정
EDITION = PJ["edition"]

# 반영여부 5종: dataviz 팔레트 검증 통과(CVD 최악 인접 ΔE 11.4 / 정상시력 19.3)
STATUS = OrderedDict([
    ("반영",     ("ok",   "var(--ok)")),
    ("부분반영", ("part", "var(--part)")),
    ("미반영",   ("no",   "var(--no)")),
    ("미회신",   ("none", "var(--none)")),
    ("의견없음", ("nil",  "var(--nil)")),
    ("미기재",   ("mis",  "var(--mis)")),
])
GROUP_ORDER = list(cfg.GROUP_NAMES)

# 근거 공문 대조 결과(선택 기능) · evidence_match/match_opinions.py 산출
MATCH_JSON = str(cfg.work("match_results.json"))
_EV = cfg.path("evidence_dir")
EVIDENCE_BASE = (os.path.relpath(_EV, OUT.parent).replace(os.sep, "/") + "/") if _EV else ""   # HTML 위치 기준 상대경로

# 줄 시작이 항목기호면 새 문단, 아니면 앞줄에 이어붙임(원본 PDF의 강제 개행 복원)
BULLET = re.compile(r'^\s*(?:[○●◦·・∙‧※◇□▪▫◆▶→＊*]|-\s|[①-⑳]|\(\d+\)|\d+[.)]|[【〔\[])')


def e(x):
    return html.escape(str(x), quote=False)


def unwrap(t):
    """PDF 강제 개행을 복원해 문단 리스트로 반환"""
    if not t:
        return []
    out = []
    for raw in str(t).split("\n"):
        s = raw.strip()
        if not s:
            continue
        if not out or BULLET.match(raw) or out[-1].endswith("."):
            out.append(s)          # 마침표로 끝난 줄 다음은 새 문단(원본에 표가 섞인 건 대응)
        else:
            prev = out[-1]
            sep = " " if (prev[-1].isascii() and prev[-1].isalnum()
                          and s[0].isascii() and s[0].isalnum()) else ""
            out[-1] = prev + sep + s
    return out


# ─────────────────────────────── 데이터 ───────────────────────────────
def load():
    wb = openpyxl.load_workbook(SRC, data_only=True)
    ws = wb["협의의견대장"]
    hdr = [c.value for c in ws[1]]
    idx = {h: i for i, h in enumerate(hdr)}

    recs = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r[idx["연번"]]:
            continue
        g = lambda k: (r[idx[k]] if r[idx[k]] not in (None, "") else "")
        recs.append({
            "n": int(r[idx["연번"]]),
            "kind": g("구분"),
            "grp": g("기관군"),
            "org": g("관계기관"),
            "dept": g("소관부서"),
            "team": g("팀"),
            "doc": g("접수문서번호"),
            "date": g("시행일자"),
            "law": g("근거법령"),
            "op": unwrap(g("협의의견")),
            "ac": unwrap(g("조치계획")),
            "rop": str(g("협의의견")),          # 원본 줄바꿈 그대로(대조용)
            "rac": str(g("조치계획")),
            "st": g("반영여부"),
            "re": "Y" if g("재협의") == "Y" else "",
            "iss": g("쟁점유형"),
            "note": g("비고"),
            "pg": g("출처페이지"),
        })

    # 근거 공문 연결: 연번 + 의견 지문(공백 제거 앞 20자)으로 대조해 어긋나면 붙이지 않는다.
    try:
        mr = json.load(open(MATCH_JSON, encoding="utf-8"))
    except FileNotFoundError:
        mr = {}
        print("  ⚠ match_results.json 없음 · 근거 공문 링크 생략(원문 대조는 선택 기능)")
    from urllib.parse import quote
    skew = 0
    for r in recs:
        m = mr.get(str(r["n"]))
        if not m:
            continue
        fp = re.sub(r"\s+", "", str(r["rop"])).lower()[:20]
        if fp != m.get("fp", ""):
            skew += 1
            continue
        r["mv"] = m["v"]
        r["ms"] = m["s"]
        r["ev"] = [dict(f=e["f"], d=e["d"], dt=e["dt"], p=e["p"],
                        u=EVIDENCE_BASE + quote(e["p"], safe="/"))
                   for e in m["ev"]]
    if skew:
        print(f"  ⚠ 근거 대조 지문 불일치 {skew}건 · 해당 건 링크 생략(판올림 후 재대조 필요)")

    # 기관·부서별 현황 시트 그대로 계승
    wd = wb["기관·부서별 현황"]
    depts = []
    for r in wd.iter_rows(min_row=4, values_only=True):
        if not r[0] or r[0] == "기관군":
            continue
        depts.append({
            "grp": r[0], "org": r[1], "dept": r[2], "cnt": r[3] or 0,
            "ok": r[4] or 0, "part": r[5] or 0, "no": r[6] or 0,
            "nil": r[7] or 0, "none": r[8] or 0, "mis": r[9] or 0, "re": r[10] or 0,
            # 반영률은 원본 시트 값 그대로 계승 = (반영 + 부분반영×0.5) / (계 − 의견없음 − 미회신)
            "rate": r[11],
        })
    return recs, depts


def dept_alias(recs, depts):
    """같은 부서가 표기 차이로 둘로 잡혀 부서 수가 원본 총괄표보다 늘어나는 것을 막는다.
    집계 키만 긴 표기로 맞추고 화면에 찍히는 부서명은 원본 표기를 그대로 둔다.
    별도 재협의 문서가 부서를 상위 기관 단위로만 적어 본협의 표기와 어긋나는 일이
    판마다 되풀이되어 보정을 둔다."""
    known = defaultdict(list)
    for d in depts:
        known[d["org"]].append(d["dept"])
    flat = lambda x: re.sub(r"\s+", "", str(x))
    alias = {}
    for r in recs:
        key = (r["org"], r["dept"])
        if key in alias or r["dept"] in known[r["org"]]:
            continue
        cand = [n for n in known[r["org"]] if flat(n).startswith(flat(r["dept"]))]
        if len(cand) == 1:
            alias[key] = cand[0]
            print(f"  부서명 정규화: {r['org']} {r['dept']} → {cand[0]}")
    return alias


def stats(recs, alias=None):
    alias = alias or {}
    main = [r for r in recs if r["kind"] == "본협의"]
    redo = [r for r in recs if r["kind"] == "재협의"]
    etc = [r for r in recs if r["kind"] == "총괄표 미집계"]   # 원본 상세표에만 있는 행 · 집계 제외
    counted = main + redo                                     # 집계 대상 = 원본 총괄표 + 재협의
    ms = Counter(r["st"] for r in main)
    reviewed = len(main) - ms["미회신"]              # 검토의견(미회신 제외) = 원본 총괄표 계
    # 미종결 = 미반영 ∪ 미기재 ∪ 재협의 문서 ∪ 본협의 중 재협의 진행 (중복 제외)
    unresolved = len({r["n"] for r in counted if r["st"] in ("미반영", "미기재")
                      or r["kind"] == "재협의" or r["re"] == "Y"})

    grp = OrderedDict()
    for gname in GROUP_ORDER:
        c = Counter(r["st"] for r in counted if r["grp"] == gname)
        grp[gname] = {s: c[s] for s in STATUS}
    iss = Counter(r["iss"] for r in counted if r["iss"])
    redoing = len(redo) + sum(1 for r in main if r["re"] == "Y")
    noresp = [{"org": r["org"], "dept": r["dept"], "grp": r["grp"]}
              for r in counted if r["st"] == "미회신"]
    return {
        "total": len(counted), "rows": len(recs), "etc": len(etc), "main": len(main), "redo": len(redo),
        "reviewed": reviewed, "ok": ms["반영"], "none": ms["미회신"],
        "unresolved": unresolved, "nore": ms["미반영"], "nmis": ms["미기재"], "redoing": redoing,
        "dup": ms["미반영"] + ms["미기재"] + redoing - unresolved, "noresp": noresp,
        "rate": f"{ms['반영'] / reviewed * 100:.1f}" if reviewed else "0",   # 반영 ÷ 검토의견
        "grp": grp, "iss": iss.most_common(),
        "orgs": len({r["org"] for r in recs}),
        "depts": len({(r["org"], alias.get((r["org"], r["dept"]), r["dept"]))
                      for r in recs}),
    }


# ─────────────────────────────── CSS ───────────────────────────────
CSS = """
/* ══════════ 토큰 ══════════ */
:root{
  /* 골격(테마 공통) */
  --sans:'IBM Plex Sans KR',-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif;
  --r-card:12px; --r-pill:999px; --r-sm:6px; --gap:8px;
  --side:216px; --util-h:56px; --nb-h:64px;
  /* 라이트 */
  --primary:#0f62fe; --primary-h:#0050e6; --blue60:#0043ce; --blue10:#edf5ff;
  --on-pri:#ffffff; --on-ink:#ffffff; --barlab:#ffffff;
  --ink:#161616; --ink-m:#525252; --ink-s:#8c8c8c; --z:#c6c6c6;
  --body:#f1f3f7; --canvas:#ffffff; --s1:#f4f4f4; --s2:#e8e8e8; --hair:#e0e0e0;
  --inv:#161616; --inv-ink:#ffffff; --inv-ink-m:#c6c6c6; --util-line:#393939;
  --uf:rgba(255,255,255,.10);
  --nav-bg:#ffffff; --nav-ink:#161616; --nav-ink-m:#6f6f6f; --nav-hover:#f0f0f0; --nav-line:#e0e0e0;
  --ok:#198038; --part:#ff832b; --no:#da1e28; --none:#8a3ffc; --nil:#6f6f6f; --mis:#d02670;
  --mark-bg:#fff8c4; --mark-ink:#161616;
  --arrow:url("data:image/svg+xml;charset=utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='%23525252' d='M8 11L3 6h10z'/%3E%3C/svg%3E");
}
:root[data-theme="dark"]{
  --primary:#4589ff; --primary-h:#78a9ff; --blue60:#a6c8ff; --blue10:rgba(69,137,255,.16);
  --on-pri:#0b0b0b; --on-ink:#0f0f0f; --barlab:rgba(0,0,0,.82);
  --ink:#f1f1f1; --ink-m:#aaaaaa; --ink-s:#7c7c7c; --z:#4d4d4d;
  --body:#0f0f0f; --canvas:#181818; --s1:#242424; --s2:#2c2c2c; --hair:#2b2b2b;
  --inv:#0f0f0f; --inv-ink:#f1f1f1; --inv-ink-m:#aaaaaa; --util-line:#303030;
  --uf:rgba(255,255,255,.08);
  --nav-bg:#0f0f0f; --nav-ink:#f1f1f1; --nav-ink-m:#aaaaaa; --nav-hover:#262626; --nav-line:#272727;
  --ok:#42be65; --part:#ff9d4d; --no:#fa4d56; --none:#be95ff; --nil:#8d8d8d; --mis:#ff7eb6;
  --mark-bg:rgba(255,214,10,.24); --mark-ink:#ffe57f;
  --arrow:url("data:image/svg+xml;charset=utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='%23aaaaaa' d='M8 11L3 6h10z'/%3E%3C/svg%3E");
  color-scheme:dark;
}
*{box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{margin:0; background:var(--body); color:var(--ink); font-family:var(--sans);
  font-size:15px; line-height:1.6; letter-spacing:.16px; -webkit-font-smoothing:antialiased;}
.wrap{max-width:1400px; margin:0 auto; padding:0 22px;}
.page{padding:calc(var(--util-h) + 8px) 0 calc(var(--nb-h) + 20px); margin-left:var(--side);}
::-webkit-scrollbar{width:12px; height:12px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:var(--s2); border-radius:8px;
  border:3px solid transparent; background-clip:content-box;}
::-webkit-scrollbar-thumb:hover{background:var(--ink-s); background-clip:content-box;}

/* ══════════ 상단 바 ══════════ */
.util{position:fixed; top:0; left:0; right:0; height:var(--util-h); z-index:90;
  background:var(--inv); color:var(--inv-ink);}
.util .in{height:100%; padding:0 16px; display:flex; align-items:center; gap:16px;}
.util .nm{display:flex; align-items:center; gap:9px; width:calc(var(--side) - 16px); flex:none;
  font-size:13.5px; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.util .nm b{font-weight:700;}
.util .nm .mk{width:26px; height:26px; flex:none; border-radius:var(--r-sm); background:var(--primary);
  display:flex; align-items:center; justify-content:center;}
.util .nm .mk svg{width:15px; height:15px; fill:var(--on-pri);}
.usearch{position:relative; flex:1 1 auto; max-width:620px;}
.usearch svg{position:absolute; left:15px; top:50%; transform:translateY(-50%);
  width:15px; height:15px; fill:var(--inv-ink-m); pointer-events:none;}
.usearch input{width:100%; height:38px; padding:0 15px 0 40px; border-radius:var(--r-pill);
  border:1px solid var(--util-line); background:var(--uf); color:var(--inv-ink);
  font-family:var(--sans); font-size:13.5px; letter-spacing:.16px; -webkit-appearance:none;}
.usearch input::placeholder{color:var(--inv-ink-m);}
.usearch input:focus{outline:none; border-color:var(--primary); background:rgba(255,255,255,.14);}
.util .rt{display:flex; align-items:center; gap:2px; margin-left:auto; font-size:12px;
  color:var(--inv-ink-m); letter-spacing:.32px; white-space:nowrap;}
.util .rt span{padding:0 12px; border-left:1px solid var(--util-line); line-height:1;}
.ico{width:36px; height:36px; margin-left:8px; flex:none; border:none; border-radius:var(--r-pill);
  background:transparent; color:var(--inv-ink); cursor:pointer;
  display:inline-flex; align-items:center; justify-content:center;}
.ico:hover{background:var(--uf);}
.ico svg{width:18px; height:18px; fill:currentColor;}
:root[data-theme="dark"] .i-moon{display:none;}
:root:not([data-theme="dark"]) .i-sun{display:none;}

/* ══════════ 좌측 네비 ══════════ */
.side{position:fixed; top:var(--util-h); bottom:0; left:0; width:var(--side); z-index:80;
  background:var(--nav-bg); border-right:1px solid var(--nav-line);
  padding:12px 8px 24px; overflow-y:auto; color:var(--nav-ink);}
.side-lnk{display:flex; align-items:center; gap:13px; height:42px; padding:0 13px;
  border-radius:var(--r-pill); color:var(--nav-ink); text-decoration:none;
  font-size:13.5px; font-weight:500; letter-spacing:.16px;}
.side-lnk:hover{background:var(--nav-hover);}
.side-lnk svg{width:19px; height:19px; fill:currentColor; flex:none; opacity:.92;}
.side-cta{display:flex; align-items:center; gap:9px; width:100%; height:42px; margin:14px 0 4px;
  padding:0 15px; border:1px solid var(--nav-line); border-radius:var(--r-pill);
  background:transparent; color:var(--nav-ink); font-family:var(--sans); font-size:13px;
  font-weight:500; letter-spacing:.16px; cursor:pointer; text-align:left;}
.side-cta:hover{background:var(--nav-hover);}
.side-cta svg{width:15px; height:15px; fill:currentColor; flex:none;}
.side-cta.on{background:var(--primary); border-color:var(--primary); color:var(--on-pri);}
.side-hr{height:1px; background:var(--nav-line); margin:12px 13px;}
.side-h{padding:6px 13px 8px; font-size:11.5px; font-weight:600; color:var(--nav-ink-m);
  letter-spacing:.32px;}
.side-list b{display:flex; align-items:center; gap:10px; padding:8px 13px; border-radius:var(--r-sm);
  font-size:13px; font-weight:500; letter-spacing:.16px; cursor:pointer;}
.side-list b:hover{background:var(--nav-hover);}
.side-list b.on{background:var(--blue10); color:var(--primary);}
.side-list b i{width:30px; height:30px; flex:none; border-radius:var(--r-sm); background:var(--s1);
  display:flex; align-items:center; justify-content:center; font-style:normal;
  font-size:11px; font-weight:600; color:var(--ink-m); font-variant-numeric:tabular-nums;}
.side-list b u{margin-left:auto; text-decoration:none; font-size:11.5px; font-weight:400;
  color:var(--nav-ink-m); font-variant-numeric:tabular-nums;}
.side-ft{padding:14px 13px 0; font-size:11px; line-height:1.6; color:var(--nav-ink-m);
  letter-spacing:.32px;}

/* ══════════ 히어로 ══════════ */
.hero{padding:26px 0 4px;}
.eyebrow{font-size:13px; font-weight:500; color:var(--ink-m); margin-bottom:12px;
  display:flex; align-items:center; gap:10px; letter-spacing:.32px;}
.eyebrow::before{content:""; width:24px; height:2px; background:var(--primary); flex:none;}
h1{font-size:36px; font-weight:600; line-height:1.2; letter-spacing:-.5px; margin:0 0 10px;}
.sub{font-size:15px; color:var(--ink-m); margin:0;}

/* ══════════ KPI ══════════ */
.kpis{display:grid; grid-template-columns:repeat(5,1fr); gap:var(--gap); margin-top:22px;}
.kpi{background:var(--canvas); border-radius:var(--r-card); padding:16px 18px 15px;
  border-left:3px solid var(--hair);}
.kpi.k-ok{border-left-color:var(--ok);} .kpi.k-none{border-left-color:var(--none);}
.kpi.k-re{border-left-color:var(--primary);} .kpi.k-un{border-left-color:var(--no);}
.kpi .lb{font-size:12.5px; color:var(--ink-m); letter-spacing:.32px; margin-bottom:6px;}
.kpi .vl{font-size:33px; font-weight:600; line-height:1.05; letter-spacing:-.5px;}
.kpi .vl small{font-size:15px; font-weight:400; color:var(--ink-m); letter-spacing:0; margin-left:5px;}
.kpi .ft{font-size:12px; color:var(--ink-s); margin-top:6px; letter-spacing:.32px;}

/* ══════════ 섹션 ══════════ */
section{margin-top:var(--gap); padding:22px 0 4px;}
.sec-h{display:flex; align-items:baseline; justify-content:space-between; gap:16px; margin-bottom:16px;}
h2{font-size:19px; font-weight:600; margin:0; letter-spacing:-.2px;}
h2::before{content:""; display:inline-block; width:3px; height:15px; background:var(--primary);
  margin-right:10px; vertical-align:-1px; border-radius:2px;}
.sec-h .hint{font-size:12.5px; color:var(--ink-s); letter-spacing:.32px;}

/* ══════════ 차트 ══════════ */
.charts{display:grid; grid-template-columns:1.06fr 1fr; gap:var(--gap);}
.chart{background:var(--canvas); border-radius:var(--r-card); padding:18px 22px 20px;}
.chart h3{font-size:14px; font-weight:600; margin:0 0 4px; letter-spacing:.16px;}
.chart .cap{font-size:12px; color:var(--ink-s); margin:0 0 16px; letter-spacing:.32px;}
.legend{display:flex; flex-wrap:wrap; gap:12px; margin-bottom:16px;}
.legend b{display:flex; align-items:center; gap:6px; font-size:12px; font-weight:400;
  color:var(--ink-m); letter-spacing:.32px;}
.legend i{width:10px; height:10px; flex:none; border-radius:3px;}
.brow{display:grid; grid-template-columns:76px 1fr 46px; align-items:center; gap:10px; margin-bottom:9px;}
.brow .nm{font-size:13px; font-weight:500; text-align:right; letter-spacing:.16px;}
.brow .tot{font-size:12.5px; color:var(--ink-m); text-align:right; font-variant-numeric:tabular-nums;}
.bar{display:flex; height:22px; background:var(--s1); border-radius:5px; overflow:hidden;}
.bar span{position:relative; cursor:pointer; margin-right:2px; transition:filter .12s;}
.bar span:last-child{margin-right:0;}
.bar span:hover{filter:brightness(1.15);}
.bar span em{position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
  font-style:normal; font-size:11px; font-weight:600; color:var(--barlab); letter-spacing:.16px;
  font-variant-numeric:tabular-nums;}
.hrow{display:grid; grid-template-columns:88px 1fr 34px; align-items:center; gap:10px; margin-bottom:7px;
  cursor:pointer;}
.hrow:hover .hb i{background:var(--primary-h);}
.hrow .nm{font-size:12.5px; text-align:right; letter-spacing:.16px; white-space:nowrap;}
.hb{height:16px; background:var(--s1); border-radius:4px; overflow:hidden;}
.hb i{display:block; height:100%; background:var(--primary); transition:background .12s;}
.hrow .vl{font-size:12.5px; font-weight:500; text-align:right; font-variant-numeric:tabular-nums;}
.nolist{margin-top:24px; padding-top:18px; border-top:1px solid var(--hair);}
.chips{display:flex; flex-wrap:wrap; gap:6px;}
.chips b{display:flex; flex-direction:column; gap:1px; background:var(--s1); padding:7px 11px;
  border-radius:var(--r-sm); border-left:3px solid var(--none);
  font-size:12.5px; font-weight:500; letter-spacing:.16px; cursor:pointer; transition:background .12s;}
.chips b:hover{background:var(--blue10); color:var(--primary);}
.chips b u{text-decoration:none; font-size:10.5px; font-weight:400; color:var(--ink-s);
  letter-spacing:.32px;}

/* ══════════ 필터 ══════════ */
.filters{display:flex; flex-wrap:wrap; align-items:center; gap:7px; margin-bottom:var(--gap);}
select{height:38px; padding:0 32px 0 14px; border:1px solid var(--hair); border-radius:var(--r-pill);
  background:var(--canvas); font-family:var(--sans); font-size:13px;
  letter-spacing:.16px; color:var(--ink); cursor:pointer; -webkit-appearance:none;
  background-image:var(--arrow); background-repeat:no-repeat;
  background-position:right 12px center; background-size:13px;}
select:hover{border-color:var(--ink-s);}
select:focus{outline:2px solid var(--primary); outline-offset:-2px;}
.chip{height:38px; padding:0 15px; border:1px solid var(--hair); border-radius:var(--r-pill);
  background:var(--canvas); font-family:var(--sans); font-size:13px; font-weight:500;
  letter-spacing:.16px; color:var(--ink-m); cursor:pointer;}
.chip:hover{border-color:var(--ink-s); color:var(--ink);}
.chip.on{background:var(--primary); border-color:var(--primary); color:var(--on-pri);}
.chip.reset{color:var(--primary);}
.fcount{margin-left:auto; font-size:13px; color:var(--ink-m); letter-spacing:.32px; white-space:nowrap;}
.fcount b{font-weight:600; color:var(--ink); font-variant-numeric:tabular-nums;}

/* ══════════ 목록 + 상세 ══════════ */
.split{display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.02fr); gap:var(--gap);}
.listwrap{background:var(--canvas); border-radius:var(--r-card); overflow:auto;
  max-height:calc(100vh - var(--util-h) - var(--nb-h) - 28px);}
.lhead{position:sticky; top:0; z-index:5; background:var(--canvas);
  border-bottom:1px solid var(--hair);
  display:grid; grid-template-columns:44px 1fr 96px; gap:9px; padding:12px 14px 9px;
  font-size:11.5px; font-weight:600; color:var(--ink-s); letter-spacing:.32px;}
.lhead span:last-child{text-align:right;}
.row{display:grid; grid-template-columns:44px 1fr 96px; gap:9px; padding:8px 8px 8px 14px;
  margin:2px 6px; border-radius:var(--r-sm); cursor:pointer; align-items:start;}
.row:hover{background:var(--s1);}
.row.sel{background:var(--blue10); box-shadow:inset 3px 0 0 var(--primary);}
.row .no{width:34px; height:34px; display:flex; align-items:center; justify-content:center;
  background:var(--s1); border-radius:var(--r-sm); font-size:11.5px; color:var(--ink-m);
  font-variant-numeric:tabular-nums; flex:none;}
.row.sel .no{background:var(--primary); color:var(--on-pri); font-weight:600;}
.row .ttl{font-size:13.5px; font-weight:500; letter-spacing:.16px; line-height:1.45; padding-top:1px;}
.row .ttl u{text-decoration:none; color:var(--ink-m); font-weight:400;}
.row.sel .ttl{color:var(--primary);}
.row.sel .ttl u{color:var(--primary); opacity:.8;}
.row .ex{font-size:12px; color:var(--ink-s); line-height:1.45; margin-top:3px;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;}
.row .rt{text-align:right; padding-top:2px;}
mark{background:var(--mark-bg); color:var(--mark-ink); padding:0 1px; border-radius:2px;}
.empty{padding:44px 20px; text-align:center; color:var(--ink-s); font-size:13.5px;}

.tag{display:inline-flex; align-items:center; gap:5px; font-size:11px; font-weight:500;
  letter-spacing:.32px; padding:3px 9px; border-radius:var(--r-pill); background:var(--s1);
  color:var(--ink-m); white-space:nowrap;}
.tag i{width:7px; height:7px; flex:none; border-radius:50%;}
.tag.ok i{background:var(--ok);} .tag.part i{background:var(--part);}
.tag.no i{background:var(--no);} .tag.none i{background:var(--none);} .tag.nil i{background:var(--nil);} .tag.mis i{background:var(--mis);}
.evi .ev-src{font-weight:400; font-size:11px; color:var(--ink-s); margin-left:6px; letter-spacing:.2px;}
.evi .ev-v{display:flex; align-items:center; gap:7px; margin:2px 0 8px; font-size:12.5px; color:var(--ink-m);}
.evi .ev-v i{width:8px; height:8px; border-radius:50%; flex:none; display:inline-block;}
.evi .ev-v i.gy{background:var(--ink-s);}
.evi .ev-f{font-size:12.5px; line-height:1.55; margin:3px 0; padding-left:15px; text-indent:-15px;}
.evi .ev-f a{color:var(--primary); text-decoration:none; word-break:break-all;}
.evi .ev-f a:hover{text-decoration:underline;}
.evi .ev-f u{text-decoration:none; color:var(--ink-s); margin-left:8px; white-space:nowrap;}
.vmark{width:8px; height:8px; border-radius:50%; display:inline-block; margin-left:6px; flex:none;}
#dmodal{position:fixed; inset:0; background:rgba(8,8,8,.62); z-index:90; display:flex;
  align-items:center; justify-content:center; padding:22px;}
#dmodal[hidden]{display:none;}
.dm-box{width:min(1080px,96vw); height:min(90vh,1300px); background:var(--canvas);
  border-radius:var(--r-card); display:flex; flex-direction:column; overflow:hidden;
  box-shadow:0 26px 70px rgba(0,0,0,.5);}
.dm-head{display:flex; align-items:center; gap:8px; padding:10px 14px;
  border-bottom:1px solid rgba(128,128,128,.25);}
.dm-head b{flex:1; min-width:0; font-size:13px; font-weight:500; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis;}
.dm-head .chip{flex:none;}
a#dm-orig{text-decoration:none; display:inline-flex; align-items:center;}
a#dm-orig[hidden]{display:none;}
.dm-body{flex:1; min-height:0; background:#3c3c3c; display:flex; align-items:center; justify-content:center;}
.dm-body iframe{width:100%; height:100%; border:0;}
.dm-pages{width:100%; height:100%; overflow:auto; -webkit-overflow-scrolling:touch; padding:12px 0;}
.dm-pages .dm-page{display:block; margin:0 auto 12px; background:#fff;
  box-shadow:0 2px 10px rgba(0,0,0,.35);}
.dm-body img{max-width:100%; max-height:100%; object-fit:contain;}
@media print{#dmodal{display:none!important;}}
.tag.re{background:var(--blue10); color:var(--blue60);}
.tag.kind{background:var(--ink); color:var(--on-ink);}
:root[data-theme="dark"] .tag.kind{background:var(--s2); color:var(--ink);}

/* ══════════ 상세 ══════════ */
.detail{background:var(--canvas); border-radius:var(--r-card); padding:20px 24px 26px;
  position:sticky; top:calc(var(--util-h) + var(--gap));
  max-height:calc(100vh - var(--util-h) - var(--nb-h) - 28px); overflow:auto;}
.d-top{display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-bottom:12px;
  padding-bottom:10px; border-bottom:1px solid var(--hair);}
.d-no{font-size:12px; color:var(--ink-s); letter-spacing:.32px; margin-right:2px;
  font-variant-numeric:tabular-nums;}
.d-org{font-size:23px; font-weight:600; letter-spacing:-.2px; line-height:1.25; margin:0 0 3px;}
.d-path{font-size:13px; color:var(--ink-m); letter-spacing:.16px; margin:0 0 16px;}
.d-meta{display:grid; grid-template-columns:76px 1fr; gap:1px 0; background:var(--hair);
  border-top:1px solid var(--hair); border-bottom:1px solid var(--hair); margin-bottom:20px;}
.d-meta dt{background:var(--canvas); padding:7px 0 7px 2px; font-size:12px; color:var(--ink-m);
  letter-spacing:.32px;}
.d-meta dd{background:var(--canvas); padding:7px 0; margin:0; font-size:13px; letter-spacing:.16px;}
.d-blk{margin-bottom:18px;}
.d-blk h4{font-size:12px; font-weight:600; color:var(--ink-m); letter-spacing:.32px;
  margin:0 0 8px; padding-bottom:6px; border-bottom:1px solid var(--hair);
  display:flex; align-items:center; gap:7px;}
.d-blk h4::before{content:""; width:3px; height:11px; background:var(--primary); flex:none;
  border-radius:2px;}
.d-tog{margin-left:auto; font-size:11.5px; font-weight:400; color:var(--primary); cursor:pointer;
  letter-spacing:.32px; border-bottom:1px solid transparent;}
.d-tog:hover{border-bottom-color:var(--primary);}
.d-raw{margin:0; font-family:var(--sans); font-size:13.5px; line-height:1.62; letter-spacing:.16px;
  white-space:pre-wrap; background:var(--s1); border-radius:var(--r-sm); padding:12px 13px;
  color:var(--ink-m);}
.d-blk.act h4::before{background:var(--ink-s);}
.d-blk p{margin:0 0 7px; font-size:14.5px; line-height:1.68; letter-spacing:.16px;
  text-indent:-11px; padding-left:11px;}
.d-blk p:last-child{margin-bottom:0;}
.d-blk .no-c{font-size:13.5px; color:var(--ink-s); letter-spacing:.16px;}
.d-note{background:var(--s1); border-radius:var(--r-sm); padding:11px 13px; font-size:12.5px;
  color:var(--ink-m); letter-spacing:.16px; border-left:3px solid var(--part);}

/* ══════════ 하단 바 ══════════ */
.nowbar{position:fixed; left:0; right:0; bottom:0; height:var(--nb-h); z-index:95;
  background:var(--nav-bg); border-top:1px solid var(--nav-line);}
.nb-pg{position:absolute; top:0; left:0; right:0; height:2px; background:var(--hair);}
.nb-pg i{display:block; height:100%; width:0; background:var(--primary); transition:width .2s;}
.nb-in{height:100%; display:flex; align-items:center; gap:12px;
  padding:0 20px 0 calc(var(--side) + 20px);}
.nb-nav{display:flex; align-items:center; gap:2px; flex:none;}
.nb-nav button{width:38px; height:38px; border:none; border-radius:var(--r-pill); cursor:pointer;
  background:transparent; color:var(--nav-ink); display:inline-flex; align-items:center;
  justify-content:center;}
.nb-nav button:hover:not(:disabled){background:var(--nav-hover);}
.nb-nav button:disabled{opacity:.3; cursor:default;}
.nb-nav svg{width:17px; height:17px; fill:currentColor;}
.nb-pos{flex:none; font-size:12px; color:var(--ink-s); letter-spacing:.32px;
  font-variant-numeric:tabular-nums; min-width:98px;}
.nb-pos b{font-weight:600; color:var(--ink);}
.nb-cur{flex:1 1 auto; display:flex; align-items:center; gap:10px; min-width:0;}
.nb-cur .nb-no{width:34px; height:34px; flex:none; border-radius:var(--r-sm); background:var(--primary);
  color:var(--on-pri); display:flex; align-items:center; justify-content:center;
  font-size:11.5px; font-weight:600; font-variant-numeric:tabular-nums;}
.nb-cur .nb-t{font-size:13.5px; font-weight:500; letter-spacing:.16px; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis;}
.nb-cur .nb-t u{text-decoration:none; color:var(--ink-m); font-weight:400;}
.nb-cur .nb-x{font-size:12px; color:var(--ink-s); letter-spacing:.32px; white-space:nowrap;}
.nb-ph{font-size:13px; color:var(--ink-s); letter-spacing:.16px;}
.nb-rt{flex:none; display:flex; align-items:center; gap:7px; margin-left:auto;}
.nb-rt .fcount{margin:0;}

/* ══════════ 기관·부서 표 ══════════ */
details.tbl{background:var(--canvas); border-radius:var(--r-card); padding:0 20px;}
details.tbl summary{cursor:pointer; padding:16px 0; font-size:14px; font-weight:500;
  letter-spacing:.16px; list-style:none; display:flex; align-items:center; gap:9px;}
details.tbl summary::-webkit-details-marker{display:none;}
details.tbl summary::before{content:"+"; display:inline-flex; align-items:center; justify-content:center;
  width:20px; height:20px; border-radius:var(--r-sm); background:var(--s1); color:var(--primary);
  font-weight:600; font-size:14px;}
details.tbl[open] summary::before{content:"−";}
details.tbl summary span{color:var(--ink-s); font-weight:400; font-size:12.5px; letter-spacing:.32px;}
table{width:100%; border-collapse:collapse; font-size:12.5px; letter-spacing:.16px; margin-bottom:18px;}
thead th{background:var(--s1); text-align:right; font-weight:600; color:var(--ink-m); font-size:11.5px;
  letter-spacing:.32px; padding:9px; border-bottom:1px solid var(--ink-s); white-space:nowrap;
  position:sticky; top:0;}
thead th:nth-child(-n+3){text-align:left;}
tbody td{padding:7px 9px; border-bottom:1px solid var(--hair); text-align:right;
  font-variant-numeric:tabular-nums;}
tbody td:nth-child(-n+3){text-align:left;}
tbody tr:hover{background:var(--s1);}
tbody td.z{color:var(--z);}
tbody td.rate b{font-weight:600;}
tr.grp-first td{border-top:1px solid var(--ink-s);}

/* ══════════ 각주 ══════════ */
.notes{background:var(--canvas); border-radius:var(--r-card); padding:20px 22px 24px;
  margin-top:var(--gap);}
.notes h3{font-size:13px; font-weight:600; margin:0 0 10px; letter-spacing:.16px;}
.notes p{margin:0 0 6px; font-size:12.5px; color:var(--ink-m); line-height:1.65; letter-spacing:.16px;
  text-indent:-14px; padding-left:14px;}
.notes p b{font-weight:500; color:var(--ink);}

/* ══════════ 반응형 ══════════ */
@media (max-width:1240px){
  .side{display:none;}
  .page{margin-left:0;}
  .util .nm{width:auto;}
  .nb-in{padding:0 16px;}
}
@media (max-width:1180px){
  .kpis{grid-template-columns:repeat(3,1fr);}
  .charts{grid-template-columns:1fr;}
  .split{grid-template-columns:1fr;}
  .listwrap{max-height:520px;}
  .detail{position:static; max-height:none;}
}
@media (max-width:680px){
  .wrap{padding:0 14px;} h1{font-size:27px;} .kpis{grid-template-columns:repeat(2,1fr);}
  .util .rt span{display:none;}
  .usearch{max-width:none;}
  .row{grid-template-columns:34px 1fr;} .row .rt{grid-column:2; text-align:left; margin-top:4px;}
  .row .no{width:30px; height:30px;}
  .lhead{grid-template-columns:34px 1fr;} .lhead span:last-child{display:none;}
  .nb-pos,.nb-cur .nb-x{display:none;}
}

/* ══════════ 인쇄(라이트 고정) ══════════ */
.pnote{display:none;}
@media print{
  :root,:root[data-theme="dark"]{
    --primary:#0f62fe; --primary-h:#0050e6; --blue60:#0043ce; --blue10:#edf5ff;
    --on-pri:#ffffff; --on-ink:#ffffff; --barlab:#ffffff;
    --ink:#161616; --ink-m:#525252; --ink-s:#8c8c8c; --z:#c6c6c6;
    --body:#ffffff; --canvas:#ffffff; --s1:#f4f4f4; --s2:#e8e8e8; --hair:#e0e0e0;
    --ok:#198038; --part:#ff832b; --no:#da1e28; --none:#8a3ffc; --nil:#6f6f6f; --mis:#d02670;
    --mark-bg:#fff8c4; --mark-ink:#161616;
    --r-card:0px; --r-pill:0px; --r-sm:0px; --gap:0px;
    color-scheme:light;
  }
  @page{size:A4; margin:12mm 10mm;}
  body{background:#fff; font-size:10pt;}
  .util,.side,.nowbar,.filters,.chart .legend{display:none !important;}
  .page{margin:0 !important; padding:0 !important;}
  .wrap{max-width:none; padding:0;}
  .hero{padding:0 0 6px;}
  .kpis{grid-template-columns:repeat(5,1fr) !important; gap:0;}
  .kpi{padding:12px; border:1px solid var(--hair); border-left-width:3px;}
  .kpi .ft{font-size:8.5pt;} .kpi .lb{font-size:9pt;} .kpi .vl{font-size:26pt;}
  .chips b{page-break-inside:avoid;}
  .row.sel{background:transparent !important; box-shadow:none !important;}
  .row.sel .no{background:var(--s1) !important; color:var(--ink-m) !important;}
  .row.sel .ttl,.row.sel .ttl u{color:var(--ink) !important;}
  .pnote{display:block; margin:10px 0 4px; padding:7px 10px; background:var(--s1);
    font-size:9.5pt; letter-spacing:.16px; color:var(--ink-m);}
  .pnote b{font-weight:600; color:var(--ink);}
  section{padding:10px 0; margin:0;}
  .charts{grid-template-columns:1fr 1fr; gap:10px;}
  .chart{padding:0 8px 0 0;}
  .split{grid-template-columns:1fr;}
  .listwrap{max-height:none; overflow:visible;}
  .detail{display:none;}
  .row .ex{-webkit-line-clamp:unset; display:block; color:var(--ink);}
  .row{grid-template-columns:34px 1fr 66px; margin:0; padding:6px 0;
    border-bottom:1px solid var(--hair); page-break-inside:avoid;}
  .row .no{width:auto; height:auto; background:transparent;}
  details.tbl{page-break-before:always; padding:0;} details.tbl summary{display:none;}
  .notes{padding:14px 0 0; border-top:1px solid var(--hair);}
  h1{font-size:20pt;}
}
"""

# ─────────────────────────────── JS ───────────────────────────────
JS = """
const R = window.__DATA__, ST = window.__ST__;
const $ = s => document.querySelector(s);
const el = (t, c, x) => { const n = document.createElement(t); if (c) n.className = c;
  if (x !== undefined) n.textContent = x; return n; };
const esc = s => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

let F = { q: '', kind: '', grp: '', org: '', st: '', iss: '', todo: false, verify: false };
let view = [], cur = null, raw = false;

const blob = r => [r.org, r.dept, r.team, r.iss, r.doc, r.law, r.op.join(' '), r.ac.join(' '), r.note]
  .join(' ').toLowerCase();
R.forEach(r => r._b = blob(r));

const TODO = new Set(['미반영', '부분반영', '미회신', '미기재']);
const isTodo = r => TODO.has(r.st) || r.re === 'Y' || r.kind === '재협의';
const VERIFY = new Set(['부분일치', '상이·확인불가']);
const isVerify = r => VERIFY.has(r.mv);

function apply() {
  const q = F.q.trim().toLowerCase();
  view = R.filter(r =>
    (!q || r._b.includes(q)) &&
    (!F.kind || r.kind === F.kind) && (!F.grp || r.grp === F.grp) &&
    (!F.org || r.org === F.org) && (!F.st || r.st === F.st) &&
    (!F.iss || r.iss === F.iss) && (!F.todo || isTodo(r)) && (!F.verify || isVerify(r)));
  paint();
  if (!view.length) { cur = null; detail(); }
  else if (!cur || !view.some(r => r.n === cur.n)) select(view[0], false);
  else detail();
}

function hl(text, q) {
  const t = esc(text);
  if (!q) return t;
  const i = t.toLowerCase().indexOf(q);
  return i < 0 ? t : t.slice(0, i) + '<mark>' + t.slice(i, i + q.length) + '</mark>' + t.slice(i + q.length);
}

function compKinds() {
  let rev = 0, none = 0, redo = 0, etc = 0;
  for (const r of R) {
    if (r.kind === '재협의') redo++;
    else if (r.kind === '총괄표 미집계') etc++;
    else if (r.st === '미회신') none++;
    else rev++;
  }
  return {rev, none, redo, etc};
}

function paint() {
  const box = $('#list'), q = F.q.trim().toLowerCase();
  box.textContent = '';
  // 건수 표시: 걸러지지 않은 상태에서는 원본 총괄표 구성으로 풀어 쓴다(검토의견 · 미회신 · 재협의 · 미집계)
  const kk = compKinds();
  $('#cnt').innerHTML = view.length === R.length
    ? '검토의견 <b>' + kk.rev + '</b> · 미회신 ' + kk.none + ' · 재협의 ' + kk.redo + ' · 미집계 ' + kk.etc
    : '<b>' + view.length + '</b>건 / 대장 ' + R.length + '행';
  // 인쇄물에만 나오는 발췌 조건 표시
  const cond = [F.todo ? '후속조치 필요' : '', F.verify ? '원문 눈대조' : '', F.kind, F.grp, F.org, F.st,
    F.iss, F.q.trim() ? '검색 "' + F.q.trim() + '"' : ''].filter(Boolean);
  $('#pnote').innerHTML = '발췌 조건 · ' + (cond.length ? esc(cond.join(' / ')) : '전체') +
    '　→　<b>' + view.length + '건</b> (대장 ' + R.length + '행 = 검토의견 ' + kk.rev + ' · 미회신 ' + kk.none + ' · 재협의 ' + kk.redo + ' · 총괄표 미집계 ' + kk.etc + ')';
  if (!view.length) { box.append(el('div', 'empty', '조건에 맞는 협의의견이 없습니다.')); return; }
  const frag = document.createDocumentFragment();
  for (const r of view) {
    const row = el('div', 'row' + (cur && cur.n === r.n ? ' sel' : ''));
    row.dataset.n = r.n;
    row.append(el('div', 'no', r.n));
    const mid = el('div');
    const ttl = el('div', 'ttl');
    ttl.innerHTML = hl(r.org, q) + ' <u>' + hl(r.dept || '-', q) + '</u>';
    mid.append(ttl);
    const first = r.op[0] || (r.st === '미회신' ? '(회신 없음)' : '(의견 없음)');
    const ex = el('div', 'ex'); ex.innerHTML = hl(first, q); mid.append(ex);
    row.append(mid);
    const rt = el('div', 'rt');
    rt.innerHTML = '<span class="tag ' + ST[r.st] + '"><i></i>' + r.st + '</span>' +
      (r.kind === '재협의' ? '<span class="tag re">재협의</span>' : '') +
      (F.verify && isVerify(r) ? '<span class="vmark" style="background:' +
        (r.mv === '부분일치' ? 'var(--part)' : 'var(--no)') + '" title="' + r.mv +
        (r.ms ? ' ' + Math.round(r.ms * 100) + '%' : '') + '"></span>' : '');
    row.append(rt);
    frag.append(row);
  }
  box.append(frag);
}

function select(r, scroll) {
  cur = r;
  document.querySelectorAll('.row.sel').forEach(n => n.classList.remove('sel'));
  const n = document.querySelector('.row[data-n="' + r.n + '"]');
  if (n) { n.classList.add('sel');
    if (scroll) n.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
  detail();
}

const MV_DOT = {'일치': 'var(--ok)', '부분일치': 'var(--part)', '상이·확인불가': 'var(--no)'};
const MV_TXT = {
  '일치': s => '원문 확인 · 일치 ' + Math.round(s * 100) + '%',
  '부분일치': s => '원문 부분일치 ' + Math.round(s * 100) + '% · 요약·축약 또는 스캔 판독 한계',
  '상이·확인불가': s => '자동 대조 실패(' + Math.round(s * 100) + '%) · 원문 수동 확인 필요',
  '상투문구(문면대조 생략)': () => '의견없음 상투 문구 · 문면 대조 생략',
  '원문없음': () => '수령한 원문 자료에 이 부서 회신이 없음',
  '미회신(원문 없음)': () => '미회신 부서 · 근거 공문 없음',
};
function evidence(r) {
  if (!r.mv) return '';
  const files = (r.ev || []).map(e =>
    '<div class="ev-f"><a href="' + e.u + '" class="ev-open" data-p="' + esc(e.p) + '">' + esc(e.f) + '</a>' +
    (e.d ? '<u>' + esc(e.d) + (e.dt ? ' · ' + esc(e.dt) : '') + '</u>' : (e.dt ? '<u>' + esc(e.dt) + '</u>' : '')) +
    '</div>').join('');
  const dot = MV_DOT[r.mv] ? '<i style="background:' + MV_DOT[r.mv] + '"></i>' : '<i class="gy"></i>';
  const txt = (MV_TXT[r.mv] || (() => r.mv))(r.ms || 0);
  return '<div class="d-blk evi"><h4>근거 공문 <span class="ev-src">' + esc(EVIDENCE_LABEL) + '</span></h4>' +
         '<p class="ev-v">' + dot + esc(txt) + '</p>' + files + '</div>';
}

let EMBS = null;
function embs() {
  if (EMBS === null) {
    const el = document.getElementById('embdata');
    try { EMBS = el ? JSON.parse(el.textContent) : {}; } catch (e) { EMBS = {}; }
  }
  return EMBS;
}
const BLOBS = {};
function b64bytes(b64) {
  const bin = atob(b64), u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return u8;
}
function b64blob(b64, mime) {
  return URL.createObjectURL(new Blob([b64bytes(b64)], { type: mime }));
}
const PDFWORKER_B64 = '@@PDFWORKER@@';
let pdfReady = false;
function initPdfjs() {
  if (pdfReady || !window.pdfjsLib || !PDFWORKER_B64) return pdfReady;
  pdfjsLib.GlobalWorkerOptions.workerSrc =
    URL.createObjectURL(new Blob([b64bytes(PDFWORKER_B64)], { type: 'text/javascript' }));
  pdfReady = true;
  return true;
}
let pdfSeq = 0;
async function renderPdf(bytes, box) {
  // 모바일 브라우저는 iframe PDF를 못 그린다. pdf.js로 쪽마다 캔버스에 그린다.
  const seq = ++pdfSeq;
  const doc = await pdfjsLib.getDocument({ data: bytes }).promise;
  const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
  for (let i = 1; i <= doc.numPages; i++) {
    if (seq !== pdfSeq) return;                 // 다른 문서를 여는 중이면 중단
    const page = await doc.getPage(i);
    const w = Math.max(box.clientWidth - 24, 320);
    const vp0 = page.getViewport({ scale: 1 });
    const vp = page.getViewport({ scale: w / vp0.width * dpr });
    const cv = document.createElement('canvas');
    cv.width = vp.width; cv.height = vp.height;
    cv.style.width = (vp.width / dpr) + 'px';
    cv.className = 'dm-page';
    box.append(cv);
    await page.render({ canvasContext: cv.getContext('2d'), viewport: vp }).promise;
  }
}
function docUrl(p, kind) {
  const e = embs()[p], key = kind + ':' + p;
  if (!e) return null;
  if (!BLOBS[key]) BLOBS[key] = b64blob(kind === 'o' ? e.o : e.v, kind === 'o' ? e.om : e.vm);
  return BLOBS[key];
}
function openDoc(p, fallback) {
  const e = embs()[p];
  if (!e || !e.v) {
    if (e && e.o) { const a = document.createElement('a'); a.href = docUrl(p, 'o'); a.download = e.n; a.click(); return; }
    if (fallback) window.open(fallback, '_blank');
    return;
  }
  const url = docUrl(p, 'v');
  $('#dm-title').textContent = e.n;
  $('#dm-tab').onclick = () => window.open(url, '_blank');
  const dl = $('#dm-orig');
  if (e.o) { dl.hidden = false; dl.href = docUrl(p, 'o'); dl.setAttribute('download', e.n); }
  else dl.hidden = true;
  const body = $('#dm-body');
  body.textContent = '';
  pdfSeq++;
  if (e.vm.indexOf('image/') === 0) { const im = new Image(); im.src = url; body.append(im); }
  else if (e.vm === 'application/pdf' && initPdfjs()) {
    const box = document.createElement('div');
    box.className = 'dm-pages';
    body.append(box);
    renderPdf(b64bytes(e.v), box).catch(() => {
      body.textContent = '';
      const f = document.createElement('iframe'); f.src = url; body.append(f);
    });
  }
  else { const f = document.createElement('iframe'); f.src = url; body.append(f); }
  $('#dmodal').hidden = false;
  document.body.style.overflow = 'hidden';
}
function closeDoc() { $('#dmodal').hidden = true; document.body.style.overflow = ''; }
$('#dmodal').addEventListener('click', ev => { if (ev.target.id === 'dmodal') closeDoc(); });
$('#dm-close').addEventListener('click', closeDoc);
$('#detail').addEventListener('click', ev => {
  const a = ev.target.closest('a.ev-open');
  if (a) { ev.preventDefault(); openDoc(a.dataset.p, a.getAttribute('href')); }
});

function detail() {
  nowbar();
  const d = $('#detail');
  if (!cur) { d.innerHTML = '<div class="empty">좌측 목록에서 협의의견을 선택하십시오.</div>'; return; }
  const r = cur, meta = [];
  if (r.doc) meta.push(['접수문서', r.doc]);
  if (r.date) meta.push(['시행일자', r.date]);
  if (r.law) meta.push(['근거법령', r.law]);
  meta.push(['쟁점유형', r.iss || '-']);
  meta.push(['원본쪽', r.pg ? EDITION_LABEL + ' ' + r.pg + '쪽' : '-']);
  const body = (parts, raw, none) => raw
    ? '<pre class="d-raw">' + esc(raw) + '</pre>'
    : (parts.length ? parts.map(p => '<p>' + esc(p) + '</p>').join('')
                    : '<p class="no-c">' + none + '</p>');
  d.innerHTML =
    '<div class="d-top"><span class="d-no">연번 ' + r.n + '</span>' +
      '<span class="tag kind">' + r.kind + '</span>' +
      '<span class="tag ' + ST[r.st] + '"><i></i>' + r.st + '</span>' +
      (r.re === 'Y' && r.kind !== '재협의' ? '<span class="tag re">재협의 진행</span>' : '') +
      (r.op.length || r.ac.length ? '<a class="d-tog" data-raw="1">' +
        (raw ? '문장으로 정리해 보기' : '원문 줄바꿈 그대로 보기') + '</a>' : '') + '</div>' +
    '<h3 class="d-org">' + esc(r.dept || r.org) + '</h3>' +
    '<p class="d-path">' + esc(r.grp) + ' · ' + esc(r.org) + (r.team ? ' · ' + esc(r.team) : '') + '</p>' +
    '<dl class="d-meta">' + meta.map(m => '<dt>' + m[0] + '</dt><dd>' + esc(String(m[1])) + '</dd>').join('') + '</dl>' +
    '<div class="d-blk"><h4>협의의견</h4>' + body(r.op, raw ? r.rop : '',
        r.st === '미회신' ? '회신 없음(무응답)' : '제시된 의견 없음') + '</div>' +
    evidence(r) +
    '<div class="d-blk act"><h4>조치계획</h4>' +
      body(r.ac, raw ? r.rac : '', '해당 없음') + '</div>' +
    (r.note ? '<div class="d-note">비고 · ' + esc(r.note) + '</div>' : '');
  const tg = d.querySelector('.d-tog');
  if (tg) tg.onclick = () => { raw = !raw; detail(); };
  d.scrollTop = 0;
}

function orgOptions() {
  const sel = $('#f-org'), keep = F.org;
  const list = [...new Set(R.filter(r => !F.grp || r.grp === F.grp).map(r => r.org))];
  sel.textContent = '';
  sel.append(new Option('관계기관 전체', ''));
  list.forEach(o => sel.append(new Option(o, o)));
  sel.value = list.includes(keep) ? keep : (F.org = '', '');
}

// 이벤트
$('#q').addEventListener('input', ev => { F.q = ev.target.value; apply(); });
$('#f-kind').addEventListener('change', ev => { F.kind = ev.target.value; apply(); });
$('#f-grp').addEventListener('change', ev => { F.grp = ev.target.value; orgOptions(); apply(); });
$('#f-org').addEventListener('change', ev => { F.org = ev.target.value; apply(); });
$('#f-st').addEventListener('change', ev => { F.st = ev.target.value; apply(); });
$('#f-iss').addEventListener('change', ev => { F.iss = ev.target.value; apply(); });
$('#f-todo').addEventListener('click', ev => {
  F.todo = !F.todo; ev.target.classList.toggle('on', F.todo); apply();
});
$('#f-verify').addEventListener('click', ev => {
  F.verify = !F.verify; ev.target.classList.toggle('on', F.verify); apply();
});
$('#f-reset').addEventListener('click', () => {
  F = { q: '', kind: '', grp: '', org: '', st: '', iss: '', todo: false, verify: false };
  $('#q').value = ''; ['f-kind', 'f-grp', 'f-st', 'f-iss'].forEach(id => $('#' + id).value = '');
  $('#f-todo').classList.remove('on'); $('#f-verify').classList.remove('on'); orgOptions(); apply();
});
$('#list').addEventListener('click', ev => {
  const row = ev.target.closest('.row');
  if (row) select(view.find(r => r.n === +row.dataset.n), false);
});
document.querySelectorAll('[data-filter]').forEach(n => n.addEventListener('click', () => {
  const i = n.dataset.filter.indexOf('=');
  const k = n.dataset.filter.slice(0, i), v = n.dataset.filter.slice(i + 1);
  F[k] = (F[k] === v ? '' : v);
  if (k === 'q') { $('#q').value = F.q; }
  else { if (k === 'grp') orgOptions(); $('#f-' + k).value = F[k]; }
  apply();
  $('#explore').scrollIntoView({ behavior: 'smooth', block: 'start' });
}));
document.addEventListener('keydown', ev => {
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(ev.target.tagName)) {
    if (ev.key === 'Escape') { ev.target.blur(); } return;
  }
  if (ev.key === 'Escape') { closeDoc(); return; }
  if (ev.key === '/' ) { ev.preventDefault(); $('#q').focus(); return; }
  if (!cur || !view.length) return;
  const i = view.findIndex(x => x.n === cur.n);
  if (ev.key === 'ArrowDown' && i < view.length - 1) { ev.preventDefault(); select(view[i + 1], true); }
  if (ev.key === 'ArrowUp' && i > 0) { ev.preventDefault(); select(view[i - 1], true); }
});
$('#print').addEventListener('click', () => window.print());

// 걸러낸 결과를 CSV로 저장(엑셀에서 바로 열리도록 UTF-8 BOM 부착)
const COLS = [['연번','n'],['구분','kind'],['기관군','grp'],['관계기관','org'],['소관부서','dept'],
  ['팀','team'],['접수문서번호','doc'],['시행일자','date'],['근거법령','law'],['협의의견','op'],
  ['조치계획','ac'],['반영여부','st'],['재협의','re'],['쟁점유형','iss'],['비고','note'],
  ['출처페이지','pg']];
$('#f-csv').addEventListener('click', () => {
  const cell = v => {
    const s = Array.isArray(v) ? v.join('\\n') : String(v ?? '');
    return /[",\\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const rows = [COLS.map(c => c[0]).join(','),
    ...view.map(r => COLS.map(c => cell(r[c[1]])).join(','))];
  const cond = [F.todo ? '후속조치' : '', F.verify ? '원문눈대조' : '', F.kind, F.grp, F.org, F.st, F.iss,
    F.q.trim()].filter(Boolean).join('_').replace(/[\\/\\\\:*?"<>|\\s]/g, '') || '전체';
  const url = URL.createObjectURL(new Blob(['\\uFEFF' + rows.join('\\r\\n')],
    { type: 'text/csv;charset=utf-8;' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = '협의의견_' + cond + '_' + view.length + '건_' + BASE_TAG + '.csv';
  a.click();
  URL.revokeObjectURL(url);
});

// ── 하단 바: 현재 건·진행 위치·건수를 목록 상태와 동기화 ──
function nowbar() {
  const i = cur ? view.findIndex(x => x.n === cur.n) : -1;
  $('#nb-pos').innerHTML = (i >= 0 ? i + 1 : 0) + ' / <b>' + view.length + '</b>건' +
    (view.length === R.length ? '' : ' (대장 ' + R.length + '행)');
  $('#nb-pg').style.width = (view.length && i >= 0 ? (i + 1) / view.length * 100 : 0) + '%';
  $('#nb-prev').disabled = i <= 0;
  $('#nb-next').disabled = i < 0 || i >= view.length - 1;
  $('#nb-cur').innerHTML = cur
    ? '<span class="nb-no">' + cur.n + '</span><span class="nb-t">' + esc(cur.org) +
      ' <u>' + esc(cur.dept || '-') + '</u></span>' +
      '<span class="tag ' + ST[cur.st] + '"><i></i>' + cur.st + '</span>' +
      (cur.iss ? '<span class="nb-x">' + esc(cur.iss) + '</span>' : '')
    : '<span class="nb-ph">조건에 맞는 협의의견이 없습니다.</span>';
  $('#s-todo').classList.toggle('on', F.todo);
  document.querySelectorAll('.side-list b').forEach(n =>
    n.classList.toggle('on', F.grp === n.dataset.filter.slice(4)));
}
const step = d => {
  const i = cur ? view.findIndex(x => x.n === cur.n) : -1;
  if (i + d >= 0 && i + d < view.length) select(view[i + d], true);
};
$('#nb-prev').addEventListener('click', () => step(-1));
$('#nb-next').addEventListener('click', () => step(1));
$('#nb-csv').addEventListener('click', () => $('#f-csv').click());
$('#nb-print').addEventListener('click', () => window.print());
$('#s-todo').addEventListener('click', () => $('#f-todo').click());

// ── 다크·라이트 전환(선택은 이 브라우저에 기억, 인쇄는 항상 라이트) ──
$('#theme').addEventListener('click', () => {
  const v = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = v;
  try { localStorage.setItem('hyb-theme', v); } catch (e) {}
});

orgOptions();
apply();
"""


# ─────────────────────────────── HTML 조립 ───────────────────────────────
def kpi_block(s):
    tiles = [
        ("k-", "검토의견", f"{s['reviewed']}", "", f"원본 총괄표 검토의견 계 · 미회신 {s['none']}개 부서 제외"),
        ("k-ok", "반영", f"{s['ok']}", f"{s['rate']}%", f"검토의견 {s['reviewed']}건 대비"),
        ("k-none", "미회신", f"{s['none']}", "부서", "회신 자체가 없는 소관부서"),
        ("k-re", "재협의", f"{s['redo']}", "", "2차 이상 협의 · 본협의표 통합분"),
        ("k-un", "미종결", f"{s['unresolved']}", "",
         f"미반영 {s['nore']} + 미기재 {s['nmis']} + 재협의 진행 {s['redoing']} (중복 {s['dup']} 제외)"),
    ]
    out = ['<div class="kpis">']
    for cls, lb, vl, unit, ft in tiles:
        u = f"<small>{e(unit)}</small>" if unit else ""
        out.append(f'<div class="kpi {cls}"><div class="lb">{e(lb)}</div>'
                   f'<div class="vl">{e(vl)}{u}</div><div class="ft">{e(ft)}</div></div>')
    out.append("</div>")
    return "".join(out)


def chart_group(s):
    out = ['<div class="chart"><h3>기관군별 반영 현황</h3>',
           f'<p class="cap">막대를 누르면 아래 목록이 해당 조건으로 걸러집니다 · 재협의 {s["redo"]}건 포함</p>',
           '<div class="legend">']
    for st, (cls, col) in STATUS.items():
        out.append(f'<b><i style="background:{col}"></i>{e(st)}</b>')
    out.append("</div>")
    mx = max(sum(v.values()) for v in s["grp"].values())
    for g, cnt in s["grp"].items():
        tot = sum(cnt.values())
        out.append(f'<div class="brow"><div class="nm">{e(g)}</div><div class="bar" '
                   f'style="width:{tot / mx * 100:.1f}%">')
        for st, (cls, col) in STATUS.items():
            v = cnt[st]
            if not v:
                continue
            lab = f"<em>{v}</em>" if v / mx >= .045 else ""   # 라벨이 들어갈 폭일 때만 표기
            out.append(f'<span style="background:{col};flex:{v}" data-filter="grp={e(g)}" '
                       f'title="{e(g)} · {e(st)} {v}건">{lab}</span>')
        out.append(f'</div><div class="tot">{tot}</div></div>')

    # 미회신 부서: 좌측 차트 하단, 클릭하면 목록이 해당 부서로 걸러진다
    seen, chips = set(), []
    for d in s["noresp"]:
        key = (d["org"], d["dept"])
        if key in seen:
            continue
        seen.add(key)
        same = (not d["dept"]) or d["dept"] == d["org"]
        chips.append(f'<b data-filter="q={e(d["org"])} {e(d["dept"])}" '
                     f'title="{e(d["grp"])} · {e(d["org"])}">{e(d["dept"] or d["org"])}'
                     + (f'<u>{e(d["grp"])}</u>' if same else f'<u>{e(d["org"])}</u>') + "</b>")
    out.append(f'<div class="nolist"><h3>미회신 {len(chips)}개 부서</h3>'
               '<p class="cap">협의 요청에 회신이 없는 소관부서 · 누르면 해당 부서로 목록이 걸러집니다</p>'
               f'<div class="chips">{"".join(chips)}</div></div>')
    out.append("</div>")
    return "".join(out)


def chart_issue(s):
    tot = sum(v for _, v in s["iss"])
    top_name, top_v = s["iss"][0]
    out = ['<div class="chart"><h3>쟁점유형별 건수</h3>',
           f'<p class="cap">전체 {tot}건 · {e(top_name)}이 {round(top_v * 100 / tot)}%로 최대 · 항목을 누르면 목록이 걸러집니다</p>']
    mx = top_v
    for name, v in s["iss"]:
        out.append(f'<div class="hrow" data-filter="iss={e(name)}"><div class="nm">{e(name)}</div>'
                   f'<div class="hb"><i style="width:{v / mx * 100:.1f}%"></i></div>'
                   f'<div class="vl">{v}</div></div>')
    out.append("</div>")
    return "".join(out)


def filters(recs):
    kinds = ["본협의", "재협의", "총괄표 미집계"]
    issues = [k for k, _ in Counter(r["iss"] for r in recs if r["iss"]).most_common()]
    sel = lambda i, ph, opts: (
        f'<select id="{i}"><option value="">{e(ph)}</option>' +
        "".join(f'<option value="{e(o)}">{e(o)}</option>' for o in opts) + "</select>")
    return (
        '<div class="filters">'
        + sel("f-kind", "구분 전체", kinds)
        + sel("f-grp", "기관군 전체", GROUP_ORDER)
        + '<select id="f-org"></select>'
        + sel("f-st", "반영여부 전체", list(STATUS))
        + sel("f-iss", "쟁점유형 전체", issues)
        + f'<button class="chip" id="f-todo" title="미반영·부분반영·미회신·미기재 및 재협의 진행 건">'
          f'후속조치 필요 {todo_count(recs)}</button>'
        + f'<button class="chip" id="f-verify" title="원문 대조가 부분일치·상이로 나온 건 · 요약 재구성·스캔 판독을 원문 실물로 눈 대조할 대상">원문 눈대조 {verify_count(recs)}</button>'
        '<button class="chip reset" id="f-reset">초기화</button>'
        '<button class="chip csv" id="f-csv" title="지금 걸러낸 결과를 엑셀에서 열 수 있는 '
        'CSV로 저장">CSV 저장</button>'
        '<div class="fcount" id="cnt"></div></div>')


def verify_count(recs):
    """원문 대조가 부분일치·상이로 나온 건(사람이 원문으로 확인할 대상)"""
    return sum(1 for r in recs if r.get("mv") in ("부분일치", "상이·확인불가"))


def todo_count(recs):
    """미반영·부분반영·미회신 또는 재협의 관련 건"""
    return sum(1 for r in recs if r["kind"] != "총괄표 미집계"
               and (r["st"] in ("미반영", "부분반영", "미회신", "미기재")
                    or r["re"] == "Y" or r["kind"] == "재협의"))


# 아이콘(Carbon 32 viewBox)
IC = {
    "home": "M16.612 2.214a1.01 1.01 0 00-1.242 0L1 13.419l1.243 1.572L4 13.621V26a2.004 2.004 0 002 "
            "2h20a2.004 2.004 0 002-2V13.63L29.757 15 31 13.428zM18 26h-4v-8h4zm2 0v-8a2.002 2.002 0 "
            "00-2-2h-4a2.002 2.002 0 00-2 2v8H6V12.062l10-7.79 10 7.8V26z",
    "list": "M10 6h18v2H10zm0 8h18v2H10zm0 8h18v2H10zM4 6h2v2H4zm0 8h2v2H4zm0 8h2v2H4z",
    "table": "M28 4H4a2 2 0 00-2 2v20a2 2 0 002 2h24a2 2 0 002-2V6a2 2 0 00-2-2zM12 26H4v-6h8zm0-8H4v-6h8"
             "zm2 8v-6h14v6zm14-8H14v-6h14zM4 10V6h24v4z",
    "note": "M26 4H6a2 2 0 00-2 2v20a2 2 0 002 2h20a2 2 0 002-2V6a2 2 0 00-2-2zM6 26V6h20v20zm3-15h14v2"
            "H9zm0 6h14v2H9zm0 6h9v2H9z",
    "filter": "M18 28h-4a2 2 0 01-2-2v-7.59L4.59 11A2 2 0 014 9.59V6a2 2 0 012-2h20a2 2 0 012 2v3.59a2 2"
              " 0 01-.59 1.41L20 18.41V26a2 2 0 01-2 2zM6 6v3.59l8 8V26h4v-8.41l8-8V6z",
    "search": "M29 27.586l-7.552-7.552a11.018 11.018 0 10-1.414 1.414L27.586 29zM4 13a9 9 0 119 9 9.01 "
              "9.01 0 01-9-9z",
    "print": "M27 9h-3V4a1 1 0 00-1-1H9a1 1 0 00-1 1v5H5a3 3 0 00-3 3v9a3 3 0 003 3h3v4a1 1 0 001 1h14a1"
             " 1 0 001-1v-4h3a3 3 0 003-3v-9a3 3 0 00-3-3zM10 5h12v4H10zm12 22H10v-8h12zm5-7h-3v-2a1 1 0"
             " 00-1-1H9a1 1 0 00-1 1v2H5a1 1 0 01-1-1v-9a1 1 0 011-1h22a1 1 0 011 1v9a1 1 0 01-1 1z",
    "moon": "M13.502 5.414a15.075 15.075 0 0011.594 18.194 11.113 11.113 0 01-7.975 3.39c-.138 0-.278.00"
            "5-.418 0a11.094 11.094 0 01-3.2-21.584M14.98 3a1.002 1.002 0 00-.175.016 13.096 13.096 0 00"
            "1.825 25.981c.164.006.328 0 .49 0a13.072 13.072 0 0010.703-5.555 1.01 1.01 0 00-.783-1.565A"
            "13.08 13.08 0 0115.89 4.38 1.015 1.015 0 0014.98 3z",
    "sun": "M16 12.005a4 4 0 11-4 4 4.005 4.005 0 014-4m0-2a6 6 0 106 6 6 6 0 00-6-6zM5.394 6.813L6.81 5"
           ".399l3.505 3.506L8.9 10.319zM2 15.005h5v2H2zm3.394 10.193L8.9 21.692l1.414 1.414-3.505 3.506"
           "zM15 25.005h2v5h-2zm6.687-1.9l1.414-1.414 3.506 3.506-1.414 1.414zm3.313-8.1h5v2h-5zm-3.313-"
           "6.101l3.506-3.506 1.414 1.414-3.506 3.506z",
    "prev": "M20 24l-8-8 8-8z",
    "next": "M12 8l8 8-8 8z",
    "bars": "M6 22h4v6H6zm8-8h4v14h-4zm8-8h4v22h-4z",
}


def icon(k, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<svg{c} viewBox="0 0 32 32"><path d="{IC[k]}"/></svg>'


def side_nav(recs, s):
    """좌측 고정 네비: 앵커 이동 + 기관군 원터치 필터"""
    links = [("#top", "현황 요약", "home"), ("#explore", "전건 열람", "list"),
             ("#depts", "기관·부서 현황", "table"), ("#notes", "집계 기준", "note")]
    out = ['<nav class="side">']
    for href, label, ic in links:
        out.append(f'<a class="side-lnk" href="{href}">{icon(ic)}{e(label)}</a>')
    out.append(f'<button class="side-cta" id="s-todo">{icon("filter")}'
               f'후속조치 필요 {todo_count(recs)}건</button>')
    out.append('<div class="side-hr"></div><div class="side-h">기관군</div><div class="side-list">')
    for g, cnt in s["grp"].items():
        tot = sum(cnt.values())
        out.append(f'<b data-filter="grp={e(g)}"><i>{tot}</i>{e(g)}<u>{cnt["반영"]} 반영</u></b>')
    out.append("</div>")
    out.append(f'<div class="side-ft">기준일 {BASE_DATE}<br>원본 {EDITION} · 검토의견 {s["reviewed"]}건<br>'
               f'열람용 화면 {VERSION} · 정본은 대장 엑셀</div>')
    out.append("</nav>")
    return "".join(out)


def now_bar():
    """하단 고정 바: 현재 건 표시 + 이동 + 내보내기"""
    return (
        '<div class="nowbar"><div class="nb-pg"><i id="nb-pg"></i></div><div class="nb-in">'
        f'<div class="nb-nav"><button id="nb-prev" title="이전 건 (↑)">{icon("prev")}</button>'
        f'<button id="nb-next" title="다음 건 (↓)">{icon("next")}</button></div>'
        '<div class="nb-pos" id="nb-pos"></div>'
        '<div class="nb-cur" id="nb-cur"></div>'
        '<div class="nb-rt">'
        '<button class="chip" id="nb-csv">CSV 저장</button>'
        '<button class="chip" id="nb-print">인쇄</button></div>'
        '</div></div>')


def dept_table(depts):
    out = ['<details class="tbl" id="depts"><summary>기관·소관부서별 협의 현황 표 '
           f'<span>{len(depts)}개 부서 · 원본 총괄표와 동일 집계</span></summary>',
           '<div style="overflow-x:auto"><table><thead><tr>'
           '<th>기관군</th><th>관계기관</th><th>소관부서</th><th>협의</th><th>반영</th>'
           '<th>부분</th><th>미반영</th><th>의견없음</th><th>미회신</th><th>미기재</th><th>재협의</th><th>반영률</th>'
           '</tr></thead><tbody>']
    prev = None
    for d in depts:
        cls = ' class="grp-first"' if d["org"] != prev else ""
        prev = d["org"]
        cells = []
        for k in ("cnt", "ok", "part", "no", "nil", "none", "mis", "re"):
            v = d[k]
            cells.append(f'<td class="z">-</td>' if not v else f"<td>{v}</td>")
        rate = (f'<b>{round(d["rate"] * 100)}%</b>' if isinstance(d["rate"], (int, float))
                else '<span class="z">-</span>')
        out.append(f'<tr{cls}><td>{e(d["grp"])}</td><td>{e(d["org"])}</td><td>{e(d["dept"])}</td>'
                   + "".join(cells) + f'<td class="rate">{rate}</td></tr>')
    out.append("</tbody></table></div></details>")
    return "".join(out)


def notes(s, depts, recs):
    """집계 기준 각주. 숫자는 전부 데이터에서 계산한다(설명글에 숫자를 굳혀 쓰지 않는다)."""
    etc = [r for r in recs if r["kind"] == "총괄표 미집계"]
    etc_txt = "·".join(f"{e(r['org'])} {e(r['dept'])}" for r in etc) or "없음"
    ev_n = len({x["p"] for r in recs for x in r.get("ev", [])})
    return f"""
<div class="notes" id="notes">
<h3>집계 기준 및 유의사항</h3>
<p>1. 집계 단위는 원본 총괄표와 같다. 검토의견은 건수, 미회신은 소관부서 수로 센다.
   반영률은 미회신을 제외한 검토의견 대비 반영 건수다. 협의 대상은 {s['orgs']}개 기관 {len(depts)}개 소관부서다.
   재협의(2차 이상 협의)는 본협의 표에 통합돼 오며 부서칸·협의의견 첫머리에 ‘(2차협의)’로 표기된다.
   대장에서는 구분란으로 갈라 두어 총괄표와 그대로 대조된다.</p>
<p>2. 원본 상세표에는 있으나 총괄표가 세지 않은 행({etc_txt})은 구분란을 «총괄표 미집계»로 두고
   모든 집계에서 뺐다. 목록에서는 구분 필터로 볼 수 있다.</p>
<p>3. 부서별 반영률은 (반영 + 부분반영×0.5) ÷ (협의건수 − 의견없음 − 미회신)이며,
   상단 KPI의 {s['rate']}%는 검토의견 {s['reviewed']}건 대비 반영 {s['ok']}건이다.</p>
<p>4. 협의의견·조치계획 본문은 원본 PDF의 줄바꿈을 복원해 문장 단위로 이어 붙였다. 표기·부호는
   원문 그대로 두었고, 상세 화면의 <b>원문 줄바꿈</b>을 누르면 원본 형태로 대조할 수 있다.</p>
<p>5. 근거 공문은 {e(PJ.get("evidence_label", "회신 원문"))}이다. 참조되는 {ev_n}개 문서는 이 화면 파일 안에 내장되어
   있어 파일 하나만 옮겨도 <b>근거 공문</b> 클릭으로 원문이 열린다. 대조는 공백을 걷어낸 문자 3그램 포함률
   기준이다(일치 ≥85%, 부분일치 ≥60%).</p>
<p>6. 출처는 「{e(PJ["source_title"])}」이며, 정본은 대장 엑셀이고 이 화면은 열람용이다.</p>
</div>
"""


MIME = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def build_embed(recs):
    """근거 원문을 base64로 심는다. HWP·HWPX는 변환 PDF로 열람하고 원본은 내려받기용."""
    import base64
    if not _EV:
        return {}
    src_root = str(_EV)
    _cv = cfg.path("evidence_pdf_conv_dir")                  # HWP·HWPX를 PDF로 바꿔 둔 폴더(선택)
    conv_root = str(_cv) if _cv else os.path.join(src_root, "_pdf")
    b64 = lambda fp: base64.b64encode(open(fp, "rb").read()).decode()
    emb, miss, total = {}, [], 0
    for pth in sorted({e["p"] for r in recs for e in r.get("ev", [])}):
        full = os.path.join(src_root, pth)
        ext = os.path.splitext(pth)[1].lower()
        if not os.path.exists(full):
            miss.append(pth); continue
        ent = {"n": os.path.basename(pth)}
        if ext in MIME:
            ent["v"], ent["vm"] = b64(full), MIME[ext]
        elif ext in (".hwp", ".hwpx"):
            conv = os.path.join(conv_root, os.path.splitext(pth)[0] + ".pdf")
            if os.path.exists(conv):
                ent["v"], ent["vm"] = b64(conv), "application/pdf"
            ent["o"], ent["om"] = b64(full), "application/octet-stream"
        else:
            miss.append(pth); continue
        emb[pth] = ent
        total += sum(len(ent.get(k, "")) for k in ("v", "o"))
    print(f"  원문 임베드 {len(emb)}건 · base64 {total/1048576:.1f}MB"
          + (f" · 제외 {len(miss)}건" if miss else ""))
    for m_ in miss:
        print("    제외:", m_[:70])
    return emb


def build(recs, depts, s):
    data = [{k: v for k, v in r.items()} for r in recs]
    st_map = {k: v[0] for k, v in STATUS.items()}
    page = f"""<!DOCTYPE html>
<html lang="ko" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(PJ["screen_title"])} 대시보드 {VERSION} · {e(PJ["name"])}</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%230f0f0f'/%3E%3Cg fill='%234589ff'%3E%3Crect x='6' y='19' width='5' height='7'/%3E%3Crect x='13.5' y='13' width='5' height='13'/%3E%3Crect x='21' y='6' width='5' height='20'/%3E%3C/g%3E%3C/svg%3E">
<script>try{{var t=localStorage.getItem('hyb-theme');if(t)document.documentElement.dataset.theme=t;}}catch(e){{}}</script>
<style>@@FONTS@@{CSS}</style></head>
<body>
<header class="util"><div class="in">
  <div class="nm"><span class="mk">{icon("bars")}</span>협의의견 <b>관리대장</b></div>
  <div class="usearch">{icon("search")}
    <input type="search" id="q" placeholder="기관·부서·의견·조치계획·법령 검색   ( / 키 )"
      autocomplete="off" spellcheck="false"></div>
  <div class="rt"><span>기준일 {BASE_DATE}</span><span>원본 {EDITION}</span><span>검토의견 {s['reviewed']}건</span>
    <button class="ico" id="theme" title="다크·라이트 전환">
      {icon("moon", "i-moon")}{icon("sun", "i-sun")}</button>
    <button class="ico" id="print" title="인쇄 (라이트 서식으로 출력)">{icon("print")}</button></div>
</div></header>

{side_nav(recs, s)}

<main class="page">
<div class="hero" id="top"><div class="wrap">
  <div class="eyebrow">{e(PJ["eyebrow"])}</div>
  <h1>{e(PJ["screen_title"])} {s['reviewed']}건 현황</h1>
  <p class="sub">{s['orgs']}개 기관 · {s['depts']}개 소관부서 · 미회신 {s['none']}개 부서 · 재협의 {s['redo']}건
    · 협의기간 {PJ["period_start"]}~{BASE_DATE}</p>
  {kpi_block(s)}
</div></div>

<section><div class="wrap">
  <div class="sec-h"><h2>현황 요약</h2>
    <div class="hint">막대 클릭 → 아래 목록 연동</div></div>
  <div class="charts">{chart_group(s)}{chart_issue(s)}</div>
</div></section>

<section id="explore"><div class="wrap">
  <div class="sec-h"><h2>협의의견 전건 열람</h2>
    <div class="hint">↑↓ 이동 · / 검색 · 행 클릭 시 우측에 전문 표시</div></div>
  {filters(recs)}
  <div class="pnote" id="pnote"></div>
  <div class="split">
    <div class="listwrap">
      <div class="lhead"><span>연번</span><span>관계기관 · 소관부서 / 협의의견</span><span>반영여부</span></div>
      <div id="list"></div>
    </div>
    <div class="detail" id="detail"></div>
  </div>
</div></section>

<section><div class="wrap">{dept_table(depts)}</div></section>
<div class="wrap">{notes(s, depts, recs)}</div>
</main>
<div id="dmodal" hidden><div class="dm-box">
  <div class="dm-head"><b id="dm-title"></b>
    <button class="chip" id="dm-tab">새 탭</button>
    <a class="chip" id="dm-orig" hidden>원본 내려받기</a>
    <button class="chip" id="dm-close">닫기 (Esc)</button></div>
  <div class="dm-body" id="dm-body"></div>
</div></div>
{now_bar()}
<script id="embdata" type="application/json">@@EMB@@</script>
<script>@@PDFJS@@</script>
<script>
window.__DATA__ = {json.dumps(data, ensure_ascii=False, separators=(',', ':'))};
window.__ST__ = {json.dumps(st_map, ensure_ascii=False)};
const EDITION_LABEL = "{EDITION}", BASE_TAG = "{BASE_DATE.replace('.', '')}";
const EVIDENCE_LABEL = {json.dumps(PJ.get("evidence_label", "회신 원문"), ensure_ascii=False)};
{JS}
</script>
</body></html>"""
    import base64 as _b64
    import json as _json
    page = page.replace("@@EMB@@",
                        _json.dumps(build_embed(recs), separators=(",", ":")))
    vend = Path(__file__).parent / "vendor"
    try:
        pdfjs = (vend / "pdf.min.js").read_text(encoding="utf-8")
        worker = _b64.b64encode((vend / "pdf.worker.min.js").read_bytes()).decode()
        page = page.replace("@@PDFJS@@", pdfjs.replace("</script", "<\\/script"))
        page = page.replace("@@PDFWORKER@@", worker)
        print(f"  PDF.js 내장: 본체 {len(pdfjs)//1024}KB + 워커 {len(worker)//1024}KB(b64) · 모바일 렌더용")
    except FileNotFoundError:
        page = page.replace("@@PDFJS@@", "").replace("@@PDFWORKER@@", "")
        print("  ⚠ vendor/pdf.js 없음 · 모바일 PDF 렌더 생략(iframe만)")
    return page


def embed_fonts(page):
    """실제 사용 문자만 서브셋해 base64 임베드"""
    try:
        from fontTools import subset
    except ImportError:
        print("  ! fonttools 미설치 · 폰트 임베드 생략 (pip install fonttools brotli)")
        return page.replace("@@FONTS@@", "")
    txt = "".join(sorted(set(re.sub(r"\s+", "", page)))) + " "
    faces, tmp = [], Path(__file__).resolve().parent / "_tmp"
    tmp.mkdir(exist_ok=True)
    have = [w for w, src in WEIGHTS.items() if (FONTS / src).exists()]
    if not have:
        tmp.rmdir()
        print("  글꼴 파일 없음(html_dashboard/fonts/) · 시스템 글꼴로 표시")
        return page.replace("@@FONTS@@", "")
    for w, src in WEIGHTS.items():
        f = FONTS / src
        if not f.exists():
            continue
        out = tmp / f"{w}.woff2"
        subset.main([str(f), f"--text={txt}", "--flavor=woff2", "--layout-features=*",
                     "--no-hinting", "--ignore-missing-glyphs", f"--output-file={out}"])
        b64 = base64.b64encode(out.read_bytes()).decode()
        faces.append(f"@font-face{{font-family:'IBM Plex Sans KR';src:url(data:font/woff2;base64,{b64})"
                     f" format('woff2');font-weight:{w};font-style:normal;font-display:swap;}}")
        out.unlink()
    tmp.rmdir()
    print(f"  폰트 서브셋 {len(txt)}자 · {len(faces)}웨이트 임베드")
    return page.replace("@@FONTS@@", "".join(faces))


def main():
    """python3 build_html.py [--out 경로] [--no-fonts]

    --out      산출 경로 지정(미지정 시 정본 HTML 갱신)
    --no-fonts 폰트 임베드 생략(서식 시안 확인용 · 파일이 가벼워 반복 확인에 적합)
    """
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1]).expanduser() if "--out" in args else OUT
    if not SRC.exists():
        sys.exit(f"[중단] 원본 없음: {SRC}")
    recs, depts = load()
    s = stats(recs, dept_alias(recs, depts))
    print(f"  집계 {s['total']}건 (본협의 {s['main']} · 재협의 {s['redo']}) + 총괄표 미집계 {s['etc']}행 · 부서 {len(depts)}개")
    page = build(recs, depts, s)
    page = page.replace("@@FONTS@@", "") if "--no-fonts" in args else embed_fonts(page)
    out.write_text(page, encoding="utf-8")
    try:
        shown = out.resolve().relative_to(cfg.ROOT)
    except ValueError:
        shown = out.name
    print(f"  생성: {shown}  ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
