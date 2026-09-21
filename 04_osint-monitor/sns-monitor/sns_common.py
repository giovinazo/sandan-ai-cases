#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""수집기(collect.py)·빌더(build_web.py)·정리도구(dedupe_store.py)가 같이 쓰는 공통 규칙.

■ 같은 글 판정(post_key)
  RSS·유튜브처럼 글 주소가 고정인 곳은 URL 로 판정한다. 페이스북처럼 같은 글의 주소가
  수집할 때마다 달라지는 곳은 '계정 + 본문 앞 60자'로 같은 글을 판정한다.
  같은 계정이 같은 문구를 다른 날 또 올린 경우(해시태그 반복 등)는 '정확한 날짜'가
  서로 다르면 다른 글로 본다(same_post).

■ 시각 해석(parse_when)
  화면에 보이는 한국어 시각 표기(사용자 구현 수집원이 화면 문구를 넘길 때)를 해석한다.
  예: 페이스북식 시각 표기는 세 가지다.
    상대  '14시간' '3일' '2주'          → 대략 날짜(exact=False)
    절대  '8월 26일 오후 5:55' '8월 26일' → 정확(exact=True, 연도는 추정)
    툴팁  '2026년 9월 2일 수요일 오후 6:02' → 정확(시각 링크에 마우스를 올리면 뜬다)
  주의: 절대표기를 상대표기보다 먼저 봐야 한다. '8월 26일'의 '26일'을 '26일 전'으로
    읽으면 날짜가 20일씩 어긋난다. 기준 시각은 반드시 KST(UTC 로 두면 새벽 실행 때 하루가 밀린다).
"""
import datetime as dt
import hashlib
import re

KST = dt.timezone(dt.timedelta(hours=9), "KST")
TEXT_KEY_LEN = 60


def now_kst():
    return dt.datetime.now(KST)


# ---- 본문 정규화 · 키 --------------------------------------------------
_MORE = re.compile(r"(?:…|\.\.\.|\s)*더\s*보기\s*$")


def norm_text(t):
    """공백을 하나로 접고 페이스북 접힘 표시('… 더 보기')를 뗀다."""
    t = re.sub(r"\s+", " ", t or "").strip()
    return _MORE.sub("", t).strip()


def text_key(t):
    return norm_text(t)[:TEXT_KEY_LEN]


def post_key(p):
    """게시물 동일성 키. 주소가 고정인 플랫폼(RSS·유튜브·X 등)=URL,
    주소가 수집마다 바뀌는 플랫폼(페이스북)과 주소 없는 글=계정+본문 앞 60자 해시."""
    if p.get("platform") != "facebook" and p.get("url"):
        return f"{p.get('platform', 'web')}:{p['url']}"
    acct = (p.get("account") or p.get("author") or "").lower()
    h = hashlib.sha1(text_key(p.get("text", "")).encode("utf-8")).hexdigest()[:16]
    return f"fb:{acct}:{h}"


def same_post(prev, new):
    """키가 같아도 둘 다 정확한 날짜를 갖고 그 날짜가 다르면 다른 글이다."""
    if prev.get("exact") and new.get("exact") and prev.get("date") and new.get("date"):
        return prev["date"] == new["date"]
    return True


def resolve_key(by, p):
    """저장소(by)에 비추어 이 게시물이 들어갈 키를 정한다. 다른 글이면 날짜 변형키."""
    k = post_key(p)
    if k in by and not same_post(by[k], p):
        return f"{k}@{p['date']}"
    return k


# ---- 시각 해석 ----------------------------------------------------------
def parse_abs(s, now=None):
    """절대표기('2026년 9월 2일 수요일 오후 6:02', '8월 26일 오후 5:55', '8월 26일',
    '2026.08.26')를 해석한다. 못 읽으면 None."""
    now = now or now_kst()
    s = (s or "").strip()
    if not s:
        return None
    m = re.search(r"(20\d\d)년\s*(\d{1,2})월\s*(\d{1,2})일", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.search(r"(?<!\d)(\d{1,2})월\s*(\d{1,2})일", s)
        if m:
            mo, d = int(m.group(1)), int(m.group(2))
            # 연도 없는 표기는 1년 안의 과거로 본다
            y = now.year if (mo, d) <= (now.month, now.day) else now.year - 1
        else:
            m = re.search(r"(20\d\d)[.\-/](\d{1,2})[.\-/](\d{1,2})", s)
            if not m:
                return None
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hh = mi = None
    t = re.search(r"(오전|오후)?\s*(\d{1,2}):(\d{2})", s)
    if t:
        hh, mi = int(t.group(2)), int(t.group(3))
        if t.group(1) == "오후" and hh < 12:
            hh += 12
        if t.group(1) == "오전" and hh == 12:
            hh = 0
    try:
        base = dt.datetime(y, mo, d, hh or 0, mi or 0, tzinfo=KST)
    except ValueError:
        return None
    return {"date": base.strftime("%Y-%m-%d"),
            "iso": base.isoformat(timespec="minutes") if hh is not None else base.strftime("%Y-%m-%d"),
            "exact": True}


def parse_rel(s, now=None):
    """상대표기('14시간', '3일', '2주', '어제', '방금')를 대략 날짜로. 못 읽으면 None."""
    now = now or now_kst()
    s = (s or "").strip()
    if not s:
        return None
    if s.startswith(("방금", "지금")):
        d = now
    elif s.startswith("어제"):
        d = now - dt.timedelta(days=1)
    else:
        m = re.search(r"(\d+)\s*(분|시간|일|주)", s)
        if not m:
            return None
        n, u = int(m.group(1)), m.group(2)
        d = now - {"분": dt.timedelta(minutes=n), "시간": dt.timedelta(hours=n),
                   "일": dt.timedelta(days=n), "주": dt.timedelta(weeks=n)}[u]
    return {"date": d.strftime("%Y-%m-%d"), "iso": "", "exact": False}


def parse_when(raw, tip="", now=None):
    """툴팁(tip)이 있으면 그것을, 없으면 링크 문구(raw)를 해석한다. 절대 → 상대 순."""
    now = now or now_kst()
    for s in (tip, raw):
        r = parse_abs(s, now)
        if r:
            return r
    r = parse_rel(raw, now)
    return r or {"date": "", "iso": "", "exact": False}


def kst_date(iso):
    """ISO 시각(X 의 datetime 속성, UTC)을 KST 날짜 문자열로."""
    try:
        d = dt.datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except Exception:
        return (iso or "")[:10]
    if d.tzinfo is None:
        d = d.replace(tzinfo=KST)
    return d.astimezone(KST).strftime("%Y-%m-%d")


# ---- 병합 · 정리 ---------------------------------------------------------
def merge_post(prev, new):
    """같은 글의 기존 기록(prev)에 새 수집분(new)을 합친다.
    정확한 시각·긴 본문·이미 받은 썸네일을 우선하고, 주소는 처음 것을 유지한다."""
    out = dict(prev)
    for k in ("platform", "account", "author", "role"):
        if new.get(k):
            out[k] = new[k]
    if len(norm_text(new.get("text", ""))) > len(norm_text(prev.get("text", ""))):
        out["text"] = new["text"]
    if not out.get("url") and new.get("url"):
        out["url"] = new["url"]
    if not out.get("thumb") and new.get("thumb"):
        out["thumb"] = new["thumb"]
    if new.get("img"):
        out["img"] = new["img"]
    if new.get("exact") and not prev.get("exact"):
        out.update(date=new.get("date", ""), iso=new.get("iso", ""), exact=True)
    elif not prev.get("date") and new.get("date"):
        out.update(date=new["date"], iso=new.get("iso", ""), exact=bool(new.get("exact")))
    for k in ("when_raw", "when_tip"):
        if new.get(k):
            out[k] = new[k]
    out["first_seen"] = prev.get("first_seen", "")   # ""=추적 시작 전부터 있던 글
    out["last_seen"] = new.get("last_seen") or prev.get("last_seen") or ""
    return out


def dedupe_posts(posts):
    """목록을 키로 합친다. 앞에 나온 기록이 prev 가 된다. 반환 (합친 목록, 제거 건수)."""
    by = {}
    for p in posts:
        k = resolve_key(by, p)
        by[k] = merge_post(by[k], p) if k in by else dict(p)
    out = []
    for k, p in by.items():
        p["key"] = k
        out.append(p)
    return out, len(posts) - len(out)


def sort_posts(posts):
    return sorted(posts, key=lambda p: (p.get("date", ""), p.get("iso", "")), reverse=True)
