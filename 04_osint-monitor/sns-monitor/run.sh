#!/bin/zsh
# SNS 모아보기 일일 갱신 예시 (수집 -> 빌드 -> 배포)
#
# 쓰는 법
#   1) 아래 DIR·PY 를 자기 환경에 맞게 고친다
#   2) 손으로 하루 1회 돌리거나, cron·launchd 로 깨운다(예시: ../automation/)
#
# 안전장치
#   - 수집이 실패하거나 게시물이 0건이면 배포하지 않는다(마지막 정상본 유지)
#   - 새 글이 없으면 배포를 건너뛴다(불필요한 배포 방지)
#   - 결과는 logs/daily.log 에 남는다. 조용한 실패를 막으려면 주기적으로 확인한다

set -u
DIR="${SNS_DIR:-$HOME/osint/sns-monitor}"   # 이 폴더의 실제 위치
PY="${PY:-/usr/bin/python3}"                 # 파이썬 절대경로(which python3)
DEPLOY_CMD="${DEPLOY_CMD:-}"                 # 예: "vercel deploy --prod --yes" (web/ 폴더에서 실행)
LOG="$DIR/logs/daily.log"
export LANG=ko_KR.UTF-8 LC_ALL=ko_KR.UTF-8
mkdir -p "$DIR/logs"

cd "$DIR" || exit 1
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 갱신 시작"

  count() { "$PY" -c "import json,os;p='data/posts.json';print(json.load(open(p))['count'] if os.path.exists(p) else 0)" 2>/dev/null || echo 0; }
  before=$(count)

  # 1) 수집. 파이프로 이으면 종료코드를 놓치므로 파일로 받은 뒤 판정한다
  "$PY" collect.py > logs/last_collect.txt 2>&1
  rc=$?
  tail -16 logs/last_collect.txt
  if [[ $rc -ne 0 ]]; then
    echo "  수집 실패(exit $rc), 배포하지 않음(마지막 정상본 유지)"
    exit 1
  fi
  after=$(count)
  echo "  누적 $before -> $after"
  if [[ "$after" -eq 0 ]]; then
    echo "  수집 0건, 배포하지 않음(빈 화면 방지)"
    exit 1
  fi

  # 2) 화면 데이터 빌드
  "$PY" build_web.py 2>&1 | tail -2

  # 3) 새 글이 있을 때만 배포
  if [[ "$after" -le "$before" ]]; then
    echo "  신규 없음, 배포 건너뜀"
    echo "===== 완료 $(date '+%H:%M:%S') (변경 없음)"
    exit 0
  fi
  if [[ -n "$DEPLOY_CMD" ]]; then
    echo "  신규 $((after - before))건, 배포"
    ( cd "$DIR/web" && eval "$DEPLOY_CMD" 2>&1 | tail -3 )
  fi
  echo "===== 완료 $(date '+%H:%M:%S')"

  if [[ $(wc -l < "$LOG") -gt 500 ]]; then
    tail -400 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  fi
} 2>&1 | tee -a "$LOG"
