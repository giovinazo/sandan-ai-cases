#!/bin/bash
# 가상 예시자료로 끝까지 돌린다(GDAL 필요 없음). 결과: output/sample/지도/평면지도.html · 입체지도.html
#   bash run_sample.sh            (파이썬을 바꾸려면 PYTHON=경로 bash run_sample.sh)
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" scripts/make_sample_data.py
"$PY" scripts/tiles_nogdal.py --config sample_data/config.json
"$PY" scripts/build.py --config sample_data/config.json
"$PY" scripts/build_3d.py --config sample_data/config.json
echo
echo "열어 보십시오: output/sample/지도/평면지도.html (더블클릭)"
