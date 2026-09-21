# -*- coding: utf-8 -*-
"""전 과정 한 번에 실행: (예시 PDF 생성) → 총괄표 → 레코드 → 정규화 → 확정 → 검증 → 엑셀 → 원문 대조 → HTML → 파생 추출.

  python3 run_all.py            # 예시자료로 처음부터 끝까지
  python3 run_all.py --no-sample  # 자기 PDF로 돌릴 때(예시 PDF를 새로 만들지 않음)

검증(총괄표 대조·독립 집계)에서 불일치가 나오면 그 자리에서 멈춘다.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable

STEPS = [
    ("예시 PDF 생성", ROOT, "sample/make_sample_pdf.py", True),
    ("총괄표 판독", ROOT / "pipeline", "parse_summary.py", False),
    ("상세표 레코드", ROOT / "pipeline", "build_records.py", False),
    ("기관·부서 배정", ROOT / "pipeline", "normalize.py", False),
    ("대장 확정", ROOT / "pipeline", "finalize.py", False),
    ("검증", ROOT / "pipeline", "verify.py", False),
    ("대장 엑셀", ROOT / "pipeline", "make_dashboard.py", False),
    ("원문 대조", ROOT, "evidence_match/match_opinions.py", False),
    ("HTML 대시보드", ROOT, "html_dashboard/build_html.py", False),
    ("파생 추출", ROOT, "extract/make_keyword_extract.py", False),
]


def main():
    no_sample = "--no-sample" in sys.argv
    for name, cwd, script, sample_only in STEPS:
        if sample_only and no_sample:
            continue
        print(f"\n▶ {name}  ({script})", flush=True)
        r = subprocess.run([PY, str(ROOT / script if cwd == ROOT else cwd / script)], cwd=str(cwd))
        if r.returncode != 0:
            sys.exit(f"\n[중단] {name} 단계 실패(종료 코드 {r.returncode}). 위 출력을 확인할 것.")
    print("\n완료. 산출물은 output/ 폴더(대장 엑셀·대시보드 HTML·검증리포트·원문대조표·추출).")


if __name__ == "__main__":
    main()
