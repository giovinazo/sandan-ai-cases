#!/bin/bash
# 정사영상 GeoTIFF -> 웹지도 타일({output_dir}/tiles)  [GDAL 경로: 실제 대용량 성과품용]
#
#   bash scripts/make_tiles.sh --config config.json
#
# 순서: gdalwarp(평면직각좌표 -> EPSG:3857, 자르기) -> gdaladdo(피라미드) -> gdal2tiles --xyz
# 원 사업 실측: 18.9GB BigTIFF(2.96cm) -> 중간산출 14GB(약 4분) -> 피라미드(약 4분) -> 타일 9.7만 장(약 7분, 8코어)
# 중간산출({work_dir}/ortho_3857.tif)은 다 만든 뒤 지워도 된다.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ARGS=("$@")
PY="${PYTHON:-python3}"
cfg() { "$PY" "$HERE/config.py" get "$1" "${ARGS[@]}"; }

for t in gdalwarp gdaladdo gdal2tiles; do
  command -v "$t" >/dev/null || { echo "$t 가 없습니다. GDAL 을 설치하십시오(맥: brew install gdal)"; exit 1; }
done

SRC="$(cfg source.ortho)"
EPSG="$(cfg crs.epsg)"
BOX="$(cfg crop_box)"
read -r ZMIN ZMAX <<< "$(cfg ortho_zoom)"
OUT="$(cfg output_dir)"
WORK="$(cfg work_dir)"
PROCS="${PROCS:-4}"
[ -f "$SRC" ] || { echo "원본 정사영상이 없습니다: $SRC"; exit 1; }
mkdir -p "$OUT" "$WORK"

# 가장 큰 배율(ZMAX)의 화소 크기(웹메르카토르 m). 원본보다 조금 거칠게 잡으면 사실상 원본 그대로다
RES="$(awk -v z="$ZMAX" 'BEGIN{printf "%.8f", 40075016.685578488/(256*2^z)}')"
TE=()
[ -n "$BOX" ] && TE=(-te_srs "EPSG:$EPSG" -te $BOX)

echo "[1] 좌표계 옮기기·자르기 (화소 ${RES}m) $(date +%T)"
gdalwarp -t_srs EPSG:3857 ${TE[@]+"${TE[@]}"} -tr "$RES" "$RES" -r bilinear -b 1 -b 2 -b 3 \
  -co TILED=YES -co BLOCKXSIZE=512 -co BLOCKYSIZE=512 \
  -co COMPRESS=DEFLATE -co ZLEVEL=1 -co BIGTIFF=YES -overwrite \
  "$SRC" "$WORK/ortho_3857.tif"

echo "[2] 피라미드 $(date +%T)"
gdaladdo -r average --config COMPRESS_OVERVIEW DEFLATE "$WORK/ortho_3857.tif" 2 4 8 16 32 64

echo "[3] 타일 자르기 z${ZMIN}~${ZMAX} $(date +%T)"
# ⚠ JPEG 화질 옵션 이름은 --jpeg-quality 다(--tiledriver-jpeg-quality 아님)
gdal2tiles --xyz -z "${ZMIN}-${ZMAX}" --tiledriver=JPEG --jpeg-quality=85 \
  --processes="$PROCS" --resampling=average --webviewer=none --quiet \
  "$WORK/ortho_3857.tif" "$OUT/tiles"
find "$OUT/tiles" -name "*.xml" -delete

echo "끝 $(date +%T): $OUT/tiles"
echo "중간산출은 지워도 됩니다: rm \"$WORK/ortho_3857.tif\""
