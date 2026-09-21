#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""수집 결과(data/posts.json)를 화면용 데이터로 만든다.

keywords.json 의 그룹으로 분류하고, priority_groups 에 걸리면 우선(priority)으로 표시한다.
공식 계정의 공개 게시물만 다루므로 마스킹은 하지 않는다.
같은 글이 저장소에 겹쳐 있어도 화면에는 한 번만 나오도록 sns_common.dedupe_posts 로
한 번 더 거른다(수집기가 먼저 거르므로 평소엔 0건).

  python3 build_web.py            # web/data.js + web/data/status.json 생성
  python3 build_web.py --sample   # 가상 예시자료(sample_data/posts.json)로 생성. 네트워크 불필요

산출물
  web/data.js              전역 POSTS·META (무빌드 화면이 그대로 읽음)
  web/data/status.json     허브가 읽는 요약(수집 게시물·감지 건수)
"""
import argparse
import datetime as dt
import json
import os

from sns_common import dedupe_posts, sort_posts

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "data", "posts.json")
SAMPLE = os.path.join(HERE, "sample_data", "posts.json")
WEB = os.path.join(HERE, "web")


def load(path, d):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else d


def load_conf(name, d):
    """자기 설정(name.json)을 읽고, 없으면 예시 설정(name.example.json)으로 물러난다."""
    for fn in (f"{name}.json", f"{name}.example.json"):
        path = os.path.join(HERE, fn)
        if os.path.exists(path):
            return load(path, d)
    return d


def classify(text, kwcfg):
    """본문에서 걸린 키워드 그룹과 개별 키워드를 찾는다."""
    hit_groups, hit_words = [], []
    for grp, words in kwcfg["groups"].items():
        got = [w for w in words if w in text]
        if got:
            hit_groups.append(grp)
            hit_words += got
    priority = any(g in kwcfg.get("priority_groups", []) for g in hit_groups)
    return hit_groups, sorted(set(hit_words)), priority


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="가상 예시자료로 빌드")
    args = ap.parse_args()

    store = load(SAMPLE if args.sample else STORE, {"posts": [], "updated": ""})
    kwcfg = load_conf("keywords", {"groups": {}, "priority_groups": []})
    tg = load_conf("targets", {})
    excl = kwcfg.get("exclude", [])

    posts, removed = dedupe_posts(store["posts"])
    if removed:
        print(f"  (화면 생성 중 중복 {removed}건 제외)")

    rows = []
    for p in sort_posts(posts):
        text = p.get("text", "")
        if any(x and x in text for x in excl):
            continue
        groups, words, priority = classify(text, kwcfg)
        rows.append({
            "platform": p["platform"], "author": p["author"], "role": p["role"],
            "account": p.get("account", ""), "date": p.get("date", ""),
            "text": text, "url": p.get("url", ""), "thumb": p.get("thumb", ""),
            "groups": groups, "kw": words, "hit": bool(groups), "priority": priority,
            "first_seen": p.get("first_seen", ""),
        })

    # 정렬: 감지 우선(priority) → 감지 → 최신순
    rows.sort(key=lambda r: (r["priority"], r["hit"], r["date"]), reverse=True)

    detected = sum(1 for r in rows if r["hit"])
    priority = sum(1 for r in rows if r["priority"])
    meta = {
        "updated": store.get("updated", ""),
        "total": len(rows), "detected": detected, "priority": priority,
        "platforms": sorted({r["platform"] for r in rows}),
        "persons": [a.get("name", "") for a in tg.get("accounts", [])],   # 필터 순서
        "groups": list(kwcfg["groups"].keys()),
        "site": tg.get("site", {}),
    }

    os.makedirs(os.path.join(WEB, "data"), exist_ok=True)
    with open(os.path.join(WEB, "data.js"), "w", encoding="utf-8") as f:
        f.write("// 자동 생성 파일. build_web.py 가 다시 만든다. 직접 고치지 말 것\n")
        f.write("window.META=" + json.dumps(meta, ensure_ascii=False) + ";\n")
        f.write("window.POSTS=" + json.dumps(rows, ensure_ascii=False) + ";\n")

    # 허브용 요약(다른 도구와 같은 스키마)
    status = {
        "key": "sns", "title": "정책·현안 SNS 모아보기",
        "updated": store.get("updated", "") or dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "metrics": [
            {"label": "수집 게시물", "value": len(rows), "unit": "건"},
            {"label": "키워드 감지", "value": detected, "unit": "건"},
        ],
    }
    json.dump(status, open(os.path.join(WEB, "data", "status.json"), "w", encoding="utf-8"),
              ensure_ascii=False)

    print(f"화면 데이터 생성: {len(rows)}건 (감지 {detected} / 우선 {priority})")
    print(f"  → {os.path.join(WEB, 'data.js')}")


if __name__ == "__main__":
    main()
