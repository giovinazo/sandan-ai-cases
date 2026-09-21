#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""수집을 다시 하지 않고 config.json의 분류 규칙만 다시 적용한다.

키워드는 그대로 두고 등급 규칙(core/land/exclude)만 손봤을 때 쓴다.
  python3 reclassify.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect import classify, load_conf, DATA  # noqa: E402
from portal_client import KINDS  # noqa: E402

def main():
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)
    rules = load_conf()["classify"]
    for kind in KINDS:
        keep, dropped = [], 0
        for it in d["items"].get(kind, []):
            g = classify(it, rules)
            if g == "excluded":
                dropped += 1
                continue
            it["grade"] = g
            keep.append(it)
        d["items"][kind] = keep
        d["counts"][kind] = len(keep)
        core = sum(1 for i in keep if i["grade"] == "core")
        land = sum(1 for i in keep if i["grade"] == "land")
        print(f"  - {KINDS[kind]['name']}: {len(keep)}건 "
              f"(사업 {core} / 부지 {land} / 기타 {len(keep)-core-land} / 제외 {dropped})")
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print("  - 저장 완료")

if __name__ == "__main__":
    main()
