#!/bin/zsh
# 뉴스 대시보드 일일 수집 예시 (수집 -> 커밋 -> 푸시)
#
# 쓰는 법
#   1) 아래 DIR·PY 를 자기 환경에 맞게 고친다
#   2) cron 또는 launchd 로 15분~1시간마다 깨운다(예시: ../automation/)
#   3) 가드가 "오늘 이미 끝났으면 즉시 종료"를 판정해 하루 한 번만 돈다
#
# 참고
#   - 데이터센터 IP(깃허브 액션 러너 등)에서는 구글뉴스 RSS 가 빈 응답을 주는 경우가 있다.
#     국내 회선의 PC에서 돌리는 편이 안정적이다
#   - build.py 는 수집이 0건이면 exit 2 로 끝난다. 이때 스탬프를 남기지 않아 다음 깨움에 재시도한다
#   - 결과는 logs/daily.log 에 남는다. 조용한 실패를 막으려면 주기적으로 확인한다

set -u
DIR="${NEWS_DIR:-$HOME/osint/newsboard}"   # 이 폴더의 실제 위치
PY="${PY:-/usr/bin/python3}"                # 파이썬 절대경로(which python3)
GIT=/usr/bin/git
STAMP="$DIR/.last_run"
LOG="$DIR/logs/daily.log"
export LANG=ko_KR.UTF-8 LC_ALL=ko_KR.UTF-8

today=$(date '+%Y-%m-%d')
mkdir -p "$DIR/logs"
[[ -f "$STAMP" && "$(cat "$STAMP" 2>/dev/null)" == "$today" ]] && exit 0

# 구글뉴스에 닿는지 먼저 본다. 안 닿으면 물러나 다음 깨움에 재시도한다
code=$(/usr/bin/curl -s -o /dev/null -m 20 -w '%{http_code}' \
       "https://news.google.com/rss/search?q=test&hl=ko&gl=KR&ceid=KR:ko" 2>&1)
if [[ "$code" != "200" ]]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') 구글뉴스 접속 실패(code=$code), 다음 깨움에 재시도" >> "$LOG"
  exit 0
fi

cd "$DIR" || exit 1
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 수집 시작"
  [[ -d .git ]] && "$GIT" pull --rebase --autostash -q 2>&1 | tail -2
  # 파이프(| tail)로 이으면 종료코드가 tail 의 것이 되어 실패를 놓친다. 파일로 받은 뒤 판정한다
  "$PY" build.py --daily > "$DIR/logs/last_build.txt" 2>&1
  rc=$?
  tail -8 "$DIR/logs/last_build.txt"
  if [[ $rc -ne 0 ]]; then
    echo "  수집 실패(exit $rc), 스탬프를 남기지 않는다(다음 깨움에 재시도)"
    exit 1
  fi
  if [[ -d .git && -n "$("$GIT" status --porcelain)" ]]; then
    "$GIT" add -A
    "$GIT" commit -q -m "자동 수집 $(date '+%Y-%m-%d %H:%M')"
    "$GIT" push -q && echo "  푸시 완료(호스팅 자동 배포)"
  else
    echo "  변경 없음 또는 깃 미사용"
  fi
  echo "$today" > "$STAMP"
  echo "===== 완료 $(date '+%H:%M:%S')"
  if [[ $(wc -l < "$LOG") -gt 500 ]]; then
    tail -400 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  fi
} >> "$LOG" 2>&1
exit 0
