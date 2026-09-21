#!/bin/bash
# 수치표면모델(DSM) -> ① 음영기복 타일({output_dir}/hs) ② 표고 격자({work_dir}/dem.json)
#                      ③ (설정에 ground 가 있으면) 지반 표고 격자({work_dir}/지반고.json)
#   [GDAL 경로: 실제 대용량 성과품용]
#
#   bash scripts/build_dsm.sh --config config.json
#
# ⚠ GDAL 파이썬 바인딩(osgeo)이 있는 파이썬이 필요하다(dsm_tools.py). PY_GDAL 로 지정할 수 있다.
#   맥에서 brew 로 GDAL 을 깔면 brew 쪽 파이썬에만 osgeo 가 들어간다. 그 파이썬에는 Pillow 가
#   없을 수 있으니, 나머지 단계(build.py 등)는 Pillow·numpy 가 있는 파이썬으로 돌린다.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ARGS=("$@")
PY="${PYTHON:-python3}"
cfg() { "$PY" "$HERE/config.py" get "$1" "${ARGS[@]}"; }

for t in gdalwarp gdaldem gdal2tiles; do
  command -v "$t" >/dev/null || { echo "$t 가 없습니다. GDAL 을 설치하십시오(맥: brew install gdal)"; exit 1; }
done
PYG=""
for c in "${PY_GDAL:-}" python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  [ -n "$c" ] && "$c" -c "from osgeo import gdal" 2>/dev/null && { PYG="$c"; break; }
done
[ -n "$PYG" ] || { echo "osgeo(GDAL 파이썬)가 든 파이썬을 못 찾았습니다. PY_GDAL=경로 로 지정하십시오"; exit 1; }

SRC="$(cfg source.dsm)"
GND="$(cfg source.ground)"
NOD="$(cfg source.nodata)"
EPSG="$(cfg crs.epsg)"
BOX="$(cfg crop_box)"
read -r ZMIN ZMAX <<< "$(cfg hs_zoom)"
ZF="$(cfg hs_z_factor)"
GRID="$(cfg grid_res_m)"
OUT="$(cfg output_dir)"
WORK="$(cfg work_dir)"
PROCS="${PROCS:-4}"
[ -f "$SRC" ] || { echo "원본 DSM 이 없습니다: $SRC"; exit 1; }
mkdir -p "$OUT" "$WORK"
RES="$(awk -v z="$ZMAX" 'BEGIN{printf "%.8f", 40075016.685578488/(256*2^z)}')"
TE=()
[ -n "$BOX" ] && TE=(-te_srs "EPSG:$EPSG" -te $BOX)

# 1) 정사영상 타일과 같은 범위·좌표계로 옮긴다. 원 사업은 이 단계가 4분(13GB DSM)
if [ -f "$WORK/dsm_3857.tif" ] && [ "${REDO:-0}" != "1" ]; then
  echo "[1] 이미 있음, 건너뜀(다시 하려면 REDO=1): $WORK/dsm_3857.tif"
else
  echo "[1] 좌표계 옮기기 (화소 ${RES}m) $(date +%T)"
  gdalwarp -t_srs EPSG:3857 ${TE[@]+"${TE[@]}"} -tr "$RES" "$RES" -r bilinear \
    -srcnodata "$NOD" -dstnodata "$NOD" \
    -co TILED=YES -co BLOCKXSIZE=512 -co BLOCKYSIZE=512 \
    -co COMPRESS=DEFLATE -co ZLEVEL=1 -co BIGTIFF=YES -overwrite \
    "$SRC" "$WORK/dsm_3857.tif"
fi

# 2) 그늘. 평지는 그냥 만들면 거의 안 보인다. 높이를 부풀린다(hs_z_factor)
echo "[2] 음영기복 $(date +%T)"
gdaldem hillshade -multidirectional -compute_edges -z "$ZF" \
  -co TILED=YES -co COMPRESS=DEFLATE -co ZLEVEL=1 -co BIGTIFF=YES \
  "$WORK/dsm_3857.tif" "$WORK/hs_raw.tif"

# 3) 계조 늘리기(중앙값을 128 로). 정사영상 위에 겹쳐 보이게 하는 핵심 단계
echo "[3] 계조 늘리기 $(date +%T)"
"$PYG" "$HERE/dsm_tools.py" stretch "$WORK/hs_raw.tif" "$WORK/hs.tif"

# 4) 타일
echo "[4] 음영 타일 z${ZMIN}~${ZMAX} $(date +%T)"
rm -rf "$OUT/hs"
gdal2tiles --xyz -z "${ZMIN}-${ZMAX}" --tiledriver=JPEG --jpeg-quality=82 \
  --processes="$PROCS" --resampling=average --webviewer=none --quiet \
  "$WORK/hs.tif" "$OUT/hs"
find "$OUT/hs" -name "*.xml" -delete

# 5) 표고 격자. 약 2.4m(메르카토르) 간격이면 화면 파일에 담아도 수 MB 안쪽이다
echo "[5] 표고 격자 $(date +%T)"
gdalwarp -tr "$GRID" "$GRID" -r average -overwrite -srcnodata "$NOD" -dstnodata "$NOD" -q \
  "$WORK/dsm_3857.tif" "$WORK/dem_grid.tif"
"$PYG" "$HERE/dsm_tools.py" grid "$WORK/dem_grid.tif" "$WORK/dem.json"

# 6) 지반 표고(선택)
if [ -n "$GND" ] && [ -f "$GND" ]; then
  echo "[6] 지반 표고 격자 $(date +%T)"
  gdalwarp -t_srs EPSG:3857 ${TE[@]+"${TE[@]}"} -tr "$GRID" "$GRID" -r average -overwrite \
    -srcnodata "$NOD" -dstnodata "$NOD" -q "$GND" "$WORK/gnd_grid.tif"
  "$PYG" "$HERE/dsm_tools.py" grid "$WORK/gnd_grid.tif" "$WORK/지반고.json"
fi

echo
echo "끝 $(date +%T). 다음: python3 scripts/build.py ${ARGS[*]}"
echo "중간산출은 지워도 됩니다: $WORK/*.tif"
