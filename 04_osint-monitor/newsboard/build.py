#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
뉴스 스크랩 대시보드 데이터 빌더
  수집(구글뉴스 RSS) → 원문URL 복원 → 요약 추출 → data/news.json 생성

사용법:
  python3 build.py            # 전체 수집·빌드(과거 구간 포함, 15분 안팎)
  python3 build.py --daily    # 일일 갱신. 기본 검색어만, 신규 기사만 처리
  python3 build.py --rebuild  # 수집 없이 기존 캐시로 JSON만 재생성
  python3 build.py --selftest # 실행 환경에서 구글뉴스 접근 가능한지 점검
  python3 build.py --sample   # 가상 예시자료(sample_data/items.json)로 화면 데이터만 생성(네트워크 불필요)

설정: config.json(자기 설정, 깃 제외). 없으면 config.example.json 을 쓴다.
요청 예절: 쿼리 사이 0.4초, 원문 조회는 동시 4~6건 이하로 간격을 둔다.
"""
import json, re, sys, os, ssl, time, urllib.request, urllib.parse, html as htmlmod
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, ".cache")
OUT = os.path.join(BASE, "data", "news.json")
if "--sample" not in sys.argv:
    os.makedirs(CACHE, exist_ok=True)
os.makedirs(os.path.dirname(OUT), exist_ok=True)

KST = timezone(timedelta(hours=9))
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# ── 설정 ────────────────────────────────────────────────
# 검색어·그룹·주제 규칙은 config.json(자기 설정, 깃 제외)에서 읽는다.
# 없으면 config.example.json(공개 예시)으로 물러난다.
def load_conf():
    for name in ("config.json", "config.example.json"):
        path = os.path.join(BASE, name)
        if os.path.exists(path):
            if name != "config.json":
                print("  (config.json 없음: config.example.json 으로 실행)", flush=True)
            return json.load(open(path, encoding="utf-8"))
    sys.exit("설정 파일이 없습니다(config.json 또는 config.example.json)")


CONF = load_conf()
GROUPS = CONF["groups"]            # {"org": {...}, "site": {...}}
QUERIES = list(CONF["queries"])


# 과거 구간 보강. RSS는 쿼리당 100건 상한이라 기간을 잘라 반복 수집한다
def _period_queries():
    from datetime import date
    pq = CONF.get("period_queries") or {}
    if not pq.get("start"):
        return []
    qs = []
    y, m = (int(x) for x in pq["start"].split("-"))
    today = date.today()
    while (y, m) <= (today.year, today.month):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        for q in pq.get("monthly", []):              # 건수가 많은 검색어는 월 단위
            qs.append(f"{q} after:{y}-{m:02d}-01 before:{ny}-{nm:02d}-01")
        if m % 3 == 1:                               # 건수가 적은 검색어는 분기 단위
            ey, em = (y + 1, (m + 3) % 12 or 12) if m + 3 > 12 else (y, m + 3)
            for q in pq.get("quarterly", []):
                qs.append(f"{q} after:{y}-{m:02d}-01 before:{ey}-{em:02d}-01")
        y, m = ny, nm
    return qs


# 일일 갱신(--daily)은 기본 검색어만 돈다. 과거 구간은 이미 캐시에 있다
BASE_QUERIES = list(QUERIES)
QUERIES += _period_queries()


def active_queries():
    return BASE_QUERIES if "--daily" in sys.argv else QUERIES


# ── 주제 분류 규칙 (앞선 것부터 우선 적용) ────────────────────
TOPICS_SITE = [tuple(x) for x in CONF.get("topics", {}).get("site", [])]
TOPICS_ORG = [tuple(x) for x in CONF.get("topics", {}).get("org", [])]

SOURCE_FIX = CONF.get("source_fix", {})    # 매체명 보정 {"도메인 일부": "매체명"}


# ── 1. 수집 ────────────────────────────────────────────────
def fetch_rss(q):
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
           + "&hl=ko&gl=KR&ceid=KR:ko")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
        return r.read()


def collect():
    items = []
    for q in active_queries():
        try:
            root = ET.fromstring(fetch_rss(q))
            n = 0
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                src_el = it.find("source")
                source = (src_el.text or "").strip() if src_el is not None else ""
                m = re.match(r"^(.*) - ([^-]+)$", title)
                clean = m.group(1).strip() if m else title
                if not source and m:
                    source = m.group(2).strip()
                pub = (it.findtext("pubDate") or "").strip()
                try:
                    dt = (datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z")
                          .replace(tzinfo=timezone.utc).astimezone(KST))
                    date = dt.strftime("%Y-%m-%d")
                except Exception:
                    date = ""
                items.append({"title": clean, "link": (it.findtext("link") or "").strip(),
                              "date": date, "source": source, "query": q,
                              "desc": re.sub(r"<[^>]+>", "", it.findtext("description") or "")[:300]})
                n += 1
            print(f"  [수집] {q} → {n}건", flush=True)
        except Exception as e:
            print(f"  [실패] {q} → {e}", flush=True)
        time.sleep(0.4)
    return items


# ── 2. 관련성 필터 + 중복 제거 ─────────────────────────────
def dedupe_filter(items):
    seen, out = set(), []
    for it in items:
        key = key_of(it["title"])
        if key in seen:
            continue
        t = re.sub(r"\s+", "", it["title"] + " " + it["desc"])
        go, gs = GROUPS["org"], GROUPS["site"]
        org = (any(k.replace(" ", "") in t for k in go.get("any", []))
               or it["query"] in go.get("force_queries", []))
        site = (any(k.replace(" ", "") in t for k in gs.get("place", []))
                and any(k.replace(" ", "") in t for k in gs.get("with_any", [])))
        tag = "both" if (org and site) else ("org" if org else ("site" if site else None))
        if not tag:
            continue
        seen.add(key)
        it["tag"] = tag
        out.append(it)
    return out


# ── 3. 구글뉴스 링크 → 언론사 원문 URL 복원 ────────────────
def parse_batch(txt):
    txt = txt.lstrip(")]}'").strip()
    try:
        outer = json.loads(txt)
    except Exception:
        m = re.search(r'garturlres\\",\\"(.+?)\\",\d', txt)
        return m.group(1).encode().decode("unicode_escape") if m else None
    for row in outer:
        if isinstance(row, list) and len(row) > 2 and row[0] == "wrb.fr" and isinstance(row[2], str):
            try:
                inner = json.loads(row[2])
                if isinstance(inner, list) and len(inner) > 1 and str(inner[1]).startswith("http"):
                    return inner[1]
            except Exception:
                pass
    return None


def resolve_url(gurl, tries=3):
    for _ in range(tries):
        try:
            html = urllib.request.urlopen(
                urllib.request.Request(gurl, headers={"User-Agent": UA}),
                context=CTX, timeout=25).read().decode("utf-8", "ignore")
            sg = re.search(r'data-n-a-sg="([^"]+)"', html)
            ts = re.search(r'data-n-a-ts="([^"]+)"', html)
            aid = re.search(r'data-n-a-id="([^"]+)"', html)
            if not (sg and ts and aid):
                time.sleep(1.2); continue
            payload = [["Fbv4je", json.dumps(["garturlreq", [
                ["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
                 None, None, None, None, None, 0, 1],
                "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                aid.group(1), int(ts.group(1)), sg.group(1)]), None, "generic"]]
            body = urllib.parse.urlencode({"f.req": json.dumps([payload])}).encode()
            txt = urllib.request.urlopen(urllib.request.Request(
                "https://news.google.com/_/DotsSplashUi/data/batchexecute", data=body,
                headers={"User-Agent": UA,
                         "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}),
                context=CTX, timeout=25).read().decode("utf-8", "ignore")
            u = parse_batch(txt)
            if u:
                return u
            time.sleep(1.2)
        except Exception:
            time.sleep(1.5)
    return None


# ── 4. 원문에서 요약(og:description) 추출 ──────────────────
COMMON = ("이 ", "다.", "는 ", "을 ", "를 ", "의 ", "에 ", "했", "한다", "하는", "기업", "지원", "사업")


def korean_ok(s):
    if not s:
        return False
    return sum(1 for c in COMMON if c in s) >= 2 and len(re.findall(r"[一-鿿]", s)) < len(s) * 0.12


def broken(s):
    if not s:
        return False
    if korean_ok(s):
        return False
    try:
        if korean_ok(s.encode("cp949", "ignore").decode("utf-8", "ignore")):
            return True
    except Exception:
        pass
    return len(re.findall(r"[一-鿿]", s)) > len(s) * 0.15 or len(re.findall(r"[ㄱ-ㆎ]", s)) >= 3


def meta(h, prop):
    for pat in (rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]*content=["\']([^"\']*)["\']',
                rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']{prop}["\']'):
        m = re.search(pat, h, re.I)
        if m:
            return htmlmod.unescape(m.group(1)).strip()
    return ""


def enrich(it):
    u = it.get("url", "")
    if not u.startswith("http") or "news.google.com" in u:
        return it
    try:
        raw = urllib.request.urlopen(urllib.request.Request(
            u, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}),
            context=CTX, timeout=15).read()
        try:
            h = raw.decode("utf-8")                 # UTF-8 자체검증 우선
        except UnicodeDecodeError:
            h = raw.decode("cp949", "ignore")
        d = re.sub(r"\s+", " ", meta(h, "og:description") or meta(h, "description")).strip()
        if d and not broken(d):
            it["summary"] = d[:400]
        pt = meta(h, "article:published_time")
        if pt:
            m = re.search(r"(\d{4})[-./]?(\d{2})[-./]?(\d{2})", pt)
            if m:
                it["date_src"] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    except Exception:
        pass
    return it


# ── 5. 주제 분류 ───────────────────────────────────────────
def topic_of(it):
    text = it["title"] + " " + it.get("summary", "")
    rules = TOPICS_SITE if it["tag"] in ("site", "both") else TOPICS_ORG
    for name, kws in rules:
        if any(k in text for k in kws):
            return name
    return "기타 동향"


# ── 6. 빌드 ────────────────────────────────────────────────
def build(items):
    today = datetime.now(KST)
    out = []
    for it in items:
        date = it.get("date_src") or it.get("date") or ""
        src = it.get("source", "").strip()
        src = SOURCE_FIX.get(src, src)
        for k, v in SOURCE_FIX.items():
            if k in it.get("url", "") and (not src or src == k):
                src = v
        out.append({
            "t": it["title"],
            "u": it.get("url") or it["link"],
            "d": date,
            "s": src or "기타",
            "g": it["tag"],
            "c": topic_of(it),
            "y": (it.get("summary") or "").strip(),
        })
    out.sort(key=lambda x: x["d"], reverse=True)
    payload = {
        "updated": today.strftime("%Y-%m-%d %H:%M"),
        "total": len(out),
        "site": CONF.get("site", {}),
        "groups": {k: {"label": v.get("label", k), "short": v.get("short", k)}
                   for k, v in GROUPS.items()},
        "items": out,
    }
    json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    # 허브가 읽는 요약. news.json 은 수백 KB라 허브에서 통째로 받게 하지 않는다
    from collections import Counter as _C
    _g = _C(x["g"] for x in out)
    json.dump({
        "key": "news",
        "title": "뉴스 스크랩 대시보드",
        "updated": payload["updated"],
        "metrics": [
            {"label": "전체 기사", "value": payload["total"], "unit": "건"},
            {"label": GROUPS["site"].get("short", "사업지"),
             "value": _g.get("site", 0) + _g.get("both", 0), "unit": "건"},
        ],
    }, open(os.path.join(os.path.dirname(OUT), "status.json"), "w", encoding="utf-8"), ensure_ascii=False)

    kb = os.path.getsize(OUT) / 1024
    print(f"\n[완료] {OUT}  {len(out)}건 / {kb:.0f}KB")
    from collections import Counter
    print("  키워드:", dict(Counter(x["g"] for x in out)))
    print("  주제:", dict(Counter(x["c"] for x in out)))
    print("  기간:", out[-1]["d"], "~", out[0]["d"])
    print("  요약 확보:", sum(1 for x in out if x["y"]), "/", len(out))



def selftest():
    """실행 환경에서 구글뉴스 접근이 되는지 점검(깃허브 액션 등 외부 환경 검증용)"""
    ok = True
    print("[1] RSS 수집")
    try:
        root = ET.fromstring(fetch_rss(BASE_QUERIES[0]))
        items = list(root.iter("item"))
        print(f"    → {len(items)}건 수신")
        if len(items) < 10:
            print("    !! 수신 건수가 비정상적으로 적음"); ok = False
    except Exception as e:
        print(f"    !! 실패: {e}"); return False

    print("[2] 원문 URL 복원 (3건 표본)")
    got = 0
    for it in items[:3]:
        u = resolve_url((it.findtext("link") or "").strip())
        print(f"    → {(u or '실패')[:70]}")
        if u: got += 1
    if got == 0:
        print("    !! 전건 실패, 이 환경에서는 원문 URL 복원 불가"); ok = False
    elif got < 3:
        print(f"    ~ 부분 성공 {got}/3")

    print("[3] 원문 요약 추출 (1건)")
    if got:
        t = {"url": resolve_url((items[0].findtext("link") or "").strip()) or ""}
        enrich(t)
        s = t.get("summary", "")
        print(f"    → {(s or '(요약 없음)')[:60]}")

    print("\n결과:", "정상" if ok else "제약 있음")
    return ok


def key_of(title):
    """제목 정규화 키. 캐시 매칭과 중복 제거에 함께 쓴다"""
    return re.sub(r"[^\w가-힣]", "", title)[:40]


def main():
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)

    sample = "--sample" in sys.argv
    rebuild = "--rebuild" in sys.argv or sample
    cache_f = (os.path.join(BASE, "sample_data", "items.json") if sample
               else os.path.join(CACHE, "items.json"))

    # 누적 아카이브. 지금까지 수집한 기사 전부. 새 수집분을 여기에 더해 나간다
    archive = {}
    if os.path.exists(cache_f):
        for x in json.load(open(cache_f, encoding="utf-8")):
            archive[key_of(x["title"])] = x
    print(f"[아카이브] 기존 {len(archive)}건")

    if not rebuild:
        print(f"[1/4] 구글뉴스 RSS 수집 (쿼리 {len(active_queries())}개)")
        raw = collect()

        # 수집 0건은 정상이 아니다. 쿼리 다섯 개가 모두 빈손이면 원본이 응답하지 않은 것이다.
        # (2026-08-31: 깃허브 액션 러너에서 구글뉴스가 빈 응답을 주는데도 "성공"으로 끝나
        #  이틀치 기사가 조용히 누락됐다. 그런 실패는 반드시 오류로 드러나야 한다)
        if not raw:
            print("\n[중단] 구글뉴스 RSS 수집이 0건입니다. 원본이 응답하지 않았습니다.")
            print("       데이터센터 IP 에서는 구글이 빈 응답을 줍니다. 국내 회선에서 실행하십시오.")
            sys.exit(2)

        print(f"[2/4] 관련성 필터·중복 제거 ({len(raw)}건 →)", end=" ")
        picked = dedupe_filter(raw)
        print(f"{len(picked)}건")

        fresh = [it for it in picked if key_of(it["title"]) not in archive]
        print(f"  기보유 {len(picked)-len(fresh)}건 / 신규 {len(fresh)}건")

        if fresh:
            print("[3/4] 원문 URL 복원")
            def w1(p):
                i, it = p
                time.sleep((i % 4) * 0.25)
                it["url"] = resolve_url(it["link"]) or it["link"]
                return it
            with ThreadPoolExecutor(max_workers=4) as ex:
                list(ex.map(w1, list(enumerate(fresh))))
            print(f"  복원 {sum(1 for x in fresh if 'news.google.com' not in x['url'])}/{len(fresh)}")

            print("[4/4] 원문 요약 추출")
            def w2(p):
                i, it = p
                time.sleep((i % 6) * 0.15)
                return enrich(it)
            with ThreadPoolExecutor(max_workers=6) as ex:
                list(ex.map(w2, list(enumerate(fresh))))
            for x in fresh:
                if broken(x.get("summary", "")):
                    x["summary"] = ""
            print(f"  요약 {sum(1 for x in fresh if x.get('summary'))}/{len(fresh)}")

            for it in fresh:
                archive[key_of(it["title"])] = it

        json.dump(list(archive.values()), open(cache_f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"[아카이브] 갱신 후 {len(archive)}건")

    build(list(archive.values()))


if __name__ == "__main__":
    main()
