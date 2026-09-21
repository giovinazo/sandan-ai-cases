#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정보공개포털 모니터링 수집기.

사용법
  python3 collect.py --full     전체 이력(설정의 full_start ~ 오늘)을 훑어 새로 쌓는다
  python3 collect.py            최근분(기본 45일)만 훑어 기존 데이터에 누적한다
  python3 collect.py --days 90  최근 90일치만 훑는다

결과는 data/documents.json 한 파일에 정보목록·원문공개를 나눠 담는다.
"""

import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from portal_client import PortalClient, PortalError, KINDS, normalize  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "documents.json")
CONF = os.path.join(HERE, "config.json")                 # 자기 설정(깃 제외)
CONF_EXAMPLE = os.path.join(HERE, "config.example.json") # 예시 설정(공개)
KST = dt.timezone(dt.timedelta(hours=9))


def load_conf():
    """config.json 을 읽는다. 없으면 예시 설정으로 물러나고 그 사실을 알린다."""
    path = CONF
    if not os.path.exists(path):
        path = CONF_EXAMPLE
        print("  (config.json 없음: config.example.json 으로 실행. 자기 설정은 복사해 고칠 것)",
              file=sys.stderr)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def classify(item, rules):
    """제목을 보고 사업 직결(core) / 부지·토지(land) / 제외(excluded)를 가른다."""
    text = f"{item['title']} {item['unit_job']}"

    def hit(rule_list):
        return any(all(t in text for t in rule) for rule in rule_list)

    # 사업지 이름과 상호가 겹치는 타지역 기업 문서는 무조건 걸러낸다.
    if hit(rules.get("hard_exclude_rules", [])):
        return "excluded"

    # 학교·교육 문서는 지명만 겹치는 잡음이라 걸러낸다.
    # 다만 산단 어휘가 함께 있으면 사업 문서일 수 있으므로 살린다.
    if hit(rules.get("exclude_rules", [])):
        if not any(g in text for g in rules.get("exclude_guard", [])):
            return "excluded"

    if hit(rules.get("land_rules", [])):
        return "land"
    if hit(rules.get("core_rules", [])):
        return "core"
    return "related"


def merge(old, new):
    """id 기준으로 합치되 검색어 목록은 누적한다."""
    idx = {it["id"]: it for it in old}
    added = 0
    for it in new:
        cur = idx.get(it["id"])
        if cur:
            cur["kwds"] = sorted(set(cur.get("kwds", []) + it.get("kwds", [])))
        else:
            idx[it["id"]] = it
            added += 1
    merged = sorted(idx.values(), key=lambda x: x.get("datetime", ""), reverse=True)
    return merged, added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="전체 이력 수집")
    ap.add_argument("--days", type=int, help="최근 N일만 수집")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    conf = load_conf()
    req = conf["request"]
    today = dt.datetime.now(KST)
    end = today.strftime("%Y%m%d")
    if args.full:
        start = conf["range"]["full_start"]
        mode = "전체"
    else:
        days = args.days or conf["range"]["recent_days"]
        start = (today - dt.timedelta(days=days)).strftime("%Y%m%d")
        mode = f"최근 {days}일"

    def log(msg):
        if not args.quiet:
            print(msg, flush=True)

    log(f"■ 수집 시작 [{mode}] {start} ~ {end}")

    cli = PortalClient(timeout=req["timeout_sec"], delay=req["delay_sec"])
    buckets = {k: [] for k in KINDS}
    stats = []

    for kind in KINDS:
        cli.prepare(kind)
        for spec in conf["keywords"]:
            kwd = spec["kwd"]
            try:
                total, recs = cli.search_all(
                    kind, kwd, start, end,
                    rows=req["rows_per_page"],
                    max_pages=req["max_pages_per_keyword"],
                )
            except PortalError as e:
                log(f"  ! 중단: {e}")
                return 1
            except Exception as e:                      # 네트워크 계열
                log(f"  ! 오류({kind}/{kwd}): {e}")
                time.sleep(3)
                continue
            items = [normalize(kind, r, kwd) for r in recs]
            buckets[kind].extend(items)
            stats.append({"kind": kind, "kwd": kwd, "total": total, "got": len(items)})
            log(f"  · [{KINDS[kind]['name']}] {kwd}: 전체 {total}건 / 수집 {len(items)}건")
            time.sleep(req["delay_sec"])

    # 기존 데이터와 병합
    prev = {"items": {k: [] for k in KINDS}}
    if os.path.exists(DATA) and not args.full:
        with open(DATA, encoding="utf-8") as f:
            prev = json.load(f)

    rules = conf["classify"]
    out_items, added_cnt, drop_cnt = {}, {}, {}
    for kind in KINDS:
        graded = []
        dropped = 0
        for it in buckets[kind]:
            g = classify(it, rules)
            if g == "excluded":
                dropped += 1
                continue
            it["grade"] = g
            graded.append(it)
        merged, added = merge(prev.get("items", {}).get(kind, []), graded)
        out_items[kind] = merged
        added_cnt[kind] = added
        drop_cnt[kind] = dropped

    payload = {
        "generated_at": today.isoformat(timespec="seconds"),
        "mode": mode,
        "site": conf.get("site", {}),
        "range": {"start": start, "end": end},
        "full_start": conf["range"]["full_start"],
        "keywords": [s["kwd"] for s in conf["keywords"]],
        "query_stats": stats,
        "counts": {k: len(v) for k, v in out_items.items()},
        "added": added_cnt,
        "items": out_items,
    }
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    log("■ 수집 완료")
    for kind in KINDS:
        core = sum(1 for i in out_items[kind] if i["grade"] == "core")
        land = sum(1 for i in out_items[kind] if i["grade"] == "land")
        etc = len(out_items[kind]) - core - land
        log(f"  - {KINDS[kind]['name']}: 누적 {len(out_items[kind])}건 "
            f"(사업 {core} / 부지 {land} / 기타 {etc} / 이번 신규 {added_cnt[kind]} / 제외 {drop_cnt[kind]})")
    log(f"  - 저장: {DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
