#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""공식 계정의 공개 게시물 수집기(로그인 없이 열람 가능한 공개 피드만).

대상은 targets.json(자기 설정, 깃 제외)의 accounts 목록이다. 없으면 targets.example.json.
게시물의 요지·시각·원문링크만 담는다(전문·사진 원본은 저장하지 않는다).

  python3 collect.py                 # 전체 대상 수집
  python3 collect.py --only rss      # 특정 platform 만
  python3 collect.py --dry-run       # 저장하지 않고 결과만 출력

지원하는 platform
  rss / blog / youtube   공개 RSS·Atom 피드. 로그인 없이 누구나 열람 가능한 주소만
  custom                 sources/ 폴더의 모듈을 불러 fetch(account) 를 호출한다.
                         공식 API 등 해당 서비스 약관이 허용하는 방식으로 각자 책임 하에 구현한다.
                         (틀: sources/example_source.py)

원칙
  - 공개 게시물만. 로그인 세션·쿠키를 재사용하는 수집은 이 저장소에 넣지 않는다
  - robots.txt 가 막은 주소는 건너뛴다
  - 요청 사이 간격(REQUEST_GAP)을 둔다. 줄이지 말 것

산출물: data/posts.json (같은 글 키 기준 누적. 규칙은 sns_common.py)
"""
import argparse
import importlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from sns_common import (dedupe_posts, kst_date, merge_post, now_kst, resolve_key,
                        sort_posts)

HERE = os.path.dirname(os.path.abspath(__file__))
TARGETS = os.path.join(HERE, "targets.json")
TARGETS_EXAMPLE = os.path.join(HERE, "targets.example.json")
STORE = os.path.join(HERE, "data", "posts.json")

UA = "public-sns-monitor/1.0 (public posts digest; polite crawling)"
REQUEST_GAP = 2.5             # 요청 사이 간격(초)
TIMEOUT = 20
MAX_PER_ACCOUNT = 20          # 계정당 최근 몇 건까지
NOW = now_kst()
TODAY = NOW.strftime("%Y-%m-%d")
FEED_PLATFORMS = ("rss", "blog", "youtube")

ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"


def load_json(path, default):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def load_targets():
    if os.path.exists(TARGETS):
        return load_json(TARGETS, {})
    print("  (targets.json 없음: targets.example.json 으로 실행)")
    return load_json(TARGETS_EXAMPLE, {})


# ---- robots.txt --------------------------------------------------------
_ROBOTS = {}


def allowed(url):
    """robots.txt 가 이 주소를 막았으면 False. robots.txt 를 못 읽으면 허용으로 본다."""
    parts = urllib.parse.urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    rp = _ROBOTS.get(base)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser(base + "/robots.txt")
        try:
            req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                rp.parse(r.read().decode("utf-8", "ignore").splitlines())
        except Exception:
            rp.parse([])
        _ROBOTS[base] = rp
    return rp.can_fetch(UA, url)


# ---- 공개 피드(RSS·Atom) ------------------------------------------------
def _text(el, *names):
    for n in names:
        x = el.find(n)
        if x is not None and (x.text or "").strip():
            return x.text.strip()
    return ""


def _strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def parse_feed(raw):
    """RSS 2.0 과 Atom 을 모두 받아 [{text, iso, href}] 로 돌려준다."""
    root = ET.fromstring(raw)
    rows = []
    for it in root.iter("item"):                                  # RSS
        title = _text(it, "title")
        desc = _strip_html(_text(it, "description"))
        rows.append({"text": (title + " " + desc).strip()[:400],
                     "iso": _text(it, "pubDate"), "href": _text(it, "link")})
    for it in root.iter(ATOM + "entry"):                          # Atom(유튜브 등)
        title = _text(it, ATOM + "title")
        grp = it.find(MEDIA + "group")
        summ = _text(grp, MEDIA + "description") if grp is not None else ""
        link = it.find(ATOM + "link")
        rows.append({"text": (title + " " + _strip_html(summ)).strip()[:400],
                     "iso": _text(it, ATOM + "published", ATOM + "updated"),
                     "href": link.get("href", "") if link is not None else ""})
    return rows


def _when(s):
    """RSS(RFC 822)·Atom(ISO 8601) 시각을 (KST 날짜, iso, 정확여부)로."""
    if not s:
        return "", "", False
    try:
        iso = parsedate_to_datetime(s).isoformat()
    except Exception:
        iso = s
    return kst_date(iso), iso, True


def collect_feed(acc):
    url = acc["feed"]
    if not allowed(url):
        raise RuntimeError("robots.txt 가 막은 주소(건너뜀)")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
    posts = []
    for row in parse_feed(raw)[:MAX_PER_ACCOUNT]:
        if not row["text"]:
            continue
        date, iso, exact = _when(row["iso"])
        posts.append({
            "platform": acc["platform"], "account": acc.get("url") or url,
            "author": acc["name"], "role": acc.get("role", ""), "text": row["text"],
            "date": date, "iso": iso, "exact": exact, "url": row["href"],
        })
    return posts


# ---- 사용자 구현 소스 ----------------------------------------------------
def collect_custom(acc):
    """sources/<모듈>.py 의 fetch(account) 를 부른다. 반환 형식은 collect_feed 와 같다."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    mod = importlib.import_module(acc["module"])
    return mod.fetch(acc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="이 platform 만 수집(rss·blog·youtube·custom)")
    ap.add_argument("--dry-run", action="store_true", help="저장하지 않음")
    args = ap.parse_args()

    tg = load_targets()
    store = load_json(STORE, {"updated": "", "posts": []})
    posts, removed = dedupe_posts(store["posts"])     # 안전망(이미 정리돼 있으면 0)
    if removed:
        print(f"  (저장소 중복 {removed}건 정리)")
    by = {p["key"]: p for p in posts}

    fresh, errs, got_total = 0, [], 0
    for acc in tg.get("accounts", []):
        kind = acc.get("platform", "")
        if args.only and kind != args.only:
            continue
        label = acc.get("name", "")
        try:
            if kind in FEED_PLATFORMS:
                got = collect_feed(acc)
            elif kind == "custom":
                got = collect_custom(acc)
            else:
                print(f"  {kind:8s} {label:20s} 지원하지 않는 platform, 건너뜀")
                continue
            new = 0
            for post in got:
                post["first_seen"] = post["last_seen"] = TODAY
                key = resolve_key(by, post)
                prev = by.get(key)
                if prev is None:
                    new += 1
                    by[key] = post
                else:
                    by[key] = merge_post(prev, post)
                by[key]["key"] = key
            fresh += new
            got_total += len(got)
            print(f"  {kind:8s} {label:20s} 수집 {len(got):2d} / 신규 {new}")
        except Exception as e:
            errs.append(f"{kind}:{label}: {e}")
            print(f"  {kind:8s} {label:20s} 실패 {str(e)[:60]}")
        time.sleep(REQUEST_GAP)

    posts = sort_posts(by.values())
    print(f"\n누적 {len(posts)}건 / 이번 수집 {got_total}건 / 신규 {fresh}건")
    if errs:
        print("실패:", *errs, sep="\n  ")
    if args.dry_run:
        print("(dry-run: 저장하지 않음)")
        return 0
    store = {"updated": NOW.isoformat(timespec="seconds"), "count": len(posts), "posts": posts}
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    json.dump(store, open(STORE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"저장: {os.path.relpath(STORE, HERE)}")
    # 모든 대상이 실패했으면 조용히 넘어가지 않고 오류로 끝낸다(자동 실행이 알아채도록)
    if errs and got_total == 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
