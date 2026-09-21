#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data/documents.json 을 대시보드가 읽는 data.js 로 바꾼다.

fetch()는 file:// 에서 막히므로, 로컬에서 index.html 을 그냥 열어도 보이도록
전역 변수를 심은 js 파일로 만들어 둔다. 배포 환경에서도 그대로 동작한다.
  python3 build_web.py                 # data/documents.json -> data.js, status.json
  python3 build_web.py --mask          # 담당자 성명 가림(외부 공개 배포본)
  python3 build_web.py --sample --mask # 가상 예시자료(sample_data/)로 화면 확인. 네트워크 불필요
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "data", "documents.json")
SAMPLE = os.path.join(HERE, "sample_data", "documents.json")
OUT = os.path.join(HERE, "data.js")


def load_site():
    """화면 제목·부제. 수집 결과에 없으면 설정 파일에서 읽는다."""
    for name in ("config.json", "config.example.json"):
        path = os.path.join(HERE, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f).get("site", {})
    return {}

FIELDS = ("id", "title", "instt", "instt_se_nm", "dept", "doc_no", "charger",
          "unit_job", "date", "othbc", "file_nm", "url", "grade", "kwds")


def mask_name(nm):
    """담당자 성명을 성만 남기고 가린다 (공개 배포본 전용)."""
    nm = (nm or "").strip()
    if len(nm) < 2:
        return nm
    return nm[0] + "○" * (len(nm) - 1)


def slim(item, mask=False):
    out = {k: item.get(k, "") for k in FIELDS}
    if mask:
        out["charger"] = mask_name(out.get("charger"))
    return out


def write_status(payload, out_dir):
    """허브가 카드에 띄우는 한 줄 요약. 스키마는 네 사이트가 같이 쓴다."""
    c = payload.get("counts", {})
    status = {
        "key": "portal",
        "title": "정보공개포털 모니터링",
        "updated": payload.get("generated_at", ""),
        "metrics": [
            {"label": "수집 문서", "value": c.get("infolist", 0), "unit": "건"},
            {"label": "원문공개", "value": c.get("orginl", 0), "unit": "건"},
        ],
    }
    with open(os.path.join(out_dir, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="출력 경로 (기본 data.js)")
    ap.add_argument("--src", help="입력 경로 (기본 data/documents.json)")
    ap.add_argument("--sample", action="store_true",
                    help="가상 예시자료(sample_data/documents.json)로 빌드")
    ap.add_argument("--mask", action="store_true",
                    help="담당자 성명을 가린다. 외부 공개 배포본에 사용")
    args = ap.parse_args()
    out_path = args.out or OUT

    src = args.src or (SAMPLE if args.sample else SRC)
    if not os.path.exists(src):
        print(f"  ! 입력 파일 없음: {os.path.relpath(src, HERE)}"
              " (먼저 collect.py 를 돌리거나 --sample 로 예시 빌드)")
        return 1
    with open(src, encoding="utf-8") as f:
        d = json.load(f)

    payload = {
        "generated_at": d.get("generated_at", ""),
        "site": d.get("site") or load_site(),
        "range": d.get("range", {}),
        "full_start": d.get("full_start", ""),
        "keywords": d.get("keywords", []),
        "counts": d.get("counts", {}),
        "masked": args.mask,
        "items": {k: [slim(i, args.mask) for i in v] for k, v in d.get("items", {}).items()},
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("// 자동 생성 파일. 직접 고치지 말 것 (build_web.py 가 다시 만든다)\n")
        f.write("window.PORTAL_DATA = ")
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    # 허브(OSINT 포털)가 읽는 요약. data.js 는 850KB라 통째로 받게 하지 않는다
    write_status(payload, os.path.dirname(os.path.abspath(out_path)))

    size = os.path.getsize(out_path) / 1024
    print(f"  - {os.path.relpath(out_path, HERE)} 생성 ({size:.0f} KB"
          + (", 담당자 성명 가림)" if args.mask else ")"))
    for k, v in payload["counts"].items():
        print(f"    · {k}: {v}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
