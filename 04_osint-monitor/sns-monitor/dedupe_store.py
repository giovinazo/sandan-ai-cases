#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""누적 저장소(data/posts.json)를 정리한다(멱등. 몇 번 돌려도 결과 같음).

  python3 dedupe_store.py            # 정리 실행
  python3 dedupe_store.py --dry-run  # 결과만 보고 저장 안 함

하는 일
  1) 페이스북 절대표기 시각(when_raw '8월 26일 오후 5:55')을 새 규칙으로 다시 해석해
     날짜를 바로잡는다(옛 코드는 '26일 전'으로 읽었다). 상대표기('3일')만 남은 글은
     실행 시점을 알 수 없어 저장된 날짜를 그대로 둔다(다음 수집에서 툴팁으로 교정됨).
  2) X 는 UTC 시각을 KST 날짜로 고쳐 쓴다.
  3) 같은 글(sns_common.post_key)을 하나로 합친다. 정확한 시각·긴 본문·있는 썸네일 우선.
  4) 어느 글도 참조하지 않게 된 썸네일은 backup/<날짜>/thumbs_orphan/ 으로 옮긴다(삭제 아님).
저장 전 원본을 backup/<날짜>/posts.before_dedupe.json 에 복사한다.
"""
import argparse
import json
import os
import shutil

from sns_common import (dedupe_posts, kst_date, now_kst, parse_abs, sort_posts)

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "data", "posts.json")
THUMBS = os.path.join(HERE, "web", "thumbs")
BACKUP = os.path.join(HERE, "backup", now_kst().strftime("%Y%m%d"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    store = json.load(open(STORE, encoding="utf-8"))
    posts = store["posts"]
    n0 = len(posts)
    now = now_kst()

    fixed_fb = fixed_x = 0
    for p in posts:
        if p.get("platform") == "facebook":
            r = parse_abs(p.get("when_raw", ""), now)
            if r:
                if r["date"] != p.get("date"):
                    fixed_fb += 1
                p.update(r)
            else:
                p["exact"] = False
        else:
            d = kst_date(p.get("iso", "")) if p.get("iso") else p.get("date", "")
            if d != p.get("date"):
                fixed_x += 1
            p["date"], p["exact"] = d, bool(p.get("iso"))

    merged, removed = dedupe_posts(posts)
    merged = sort_posts(merged)

    ref = {p["thumb"] for p in merged if p.get("thumb")}
    files = sorted(os.listdir(THUMBS)) if os.path.isdir(THUMBS) else []
    orphans = [f for f in files if f"thumbs/{f}" not in ref]

    print(f"게시물 {n0} → {len(merged)} (같은 글 합침 {removed})")
    print(f"날짜 교정: 페이스북 절대표기 {fixed_fb}건 · X KST 환산 {fixed_x}건")
    print(f"썸네일 {len(files)}개 중 참조 {len(files) - len(orphans)} · 고아 {len(orphans)}")
    if args.dry_run:
        print("(dry-run: 저장하지 않음)")
        return

    os.makedirs(BACKUP, exist_ok=True)
    shutil.copy2(STORE, os.path.join(BACKUP, "posts.before_dedupe.json"))
    store = {"updated": store.get("updated", ""), "count": len(merged), "posts": merged}
    json.dump(store, open(STORE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    if orphans:
        od = os.path.join(BACKUP, "thumbs_orphan")
        os.makedirs(od, exist_ok=True)
        for f in orphans:
            shutil.move(os.path.join(THUMBS, f), os.path.join(od, f))
        print(f"고아 썸네일 {len(orphans)}개 → {od}")
    print(f"저장: {STORE} (원본 사본 {BACKUP}/posts.before_dedupe.json)")


if __name__ == "__main__":
    main()
