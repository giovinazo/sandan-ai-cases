# 뉴스 대시보드(newsboard)

관심 기관·사업지 관련 언론보도를 구글뉴스 RSS로 모아, 검색·필터·원문 이동이 되는 한 화면으로 보여준다. 수집분을 캐시에 계속 쌓아 두는 것이 핵심이다(구글뉴스 RSS는 최근분만 주므로 오늘 안 받은 기사는 곧 사라진다).

## 구성

| 파일 | 역할 |
|---|---|
| `index.html`, `assets/` | 화면(통계·필터·카드·모달). 외부 라이브러리 없음 |
| `build.py` | 수집 → 원문 주소 복원 → 요약 추출 → `data/news.json`, `data/status.json` 생성 |
| `config.example.json` | 검색어·그룹 판정 단어·주제 규칙·화면 제목 예시 |
| `sample_data/items.json` | 가상 예시자료(지어낸 매체·기사, 링크는 example.com) |
| `run_daily.sh` | 매일 자동 실행 예시 |
| `vercel.json`, `.vercelignore`, `robots.txt` | 배포 설정(검색엔진 차단 포함) |

데이터 항목은 용량을 줄이려 한 글자 키를 쓴다. `t` 제목, `u` 원문 주소, `d` 보도일, `s` 매체, `g` 그룹(org·site·both), `c` 주제, `y` 요약.

## 준비물

- Python 3.9 이상(표준 라이브러리만 사용)
- 실제 수집 시 국내 회선 인터넷

## 예시로 돌려보기

```bash
python3 build.py --sample        # sample_data -> data/news.json, data/status.json
python3 -m http.server 8000      # 화면이 fetch 로 읽으므로 파일 직접 열기 대신 웹서버로
# http://127.0.0.1:8000
```

예시 빌드 결과: 기사 18건(기관 8 · 사업지 8 · 공통 2), 주제 10종.

## 자기 설정으로 바꾸기

```bash
cp config.example.json config.json   # config.json 은 깃 제외
python3 build.py                     # 처음 1회 전체 수집(과거 구간 포함, 검색어 수에 따라 수~십수 분)
python3 build.py --daily             # 이후 매일. 기본 검색어만, 신규 기사만 처리
python3 build.py --rebuild           # 수집 없이 캐시로 JSON만 재생성(규칙만 고쳤을 때)
python3 build.py --selftest          # 이 환경에서 구글뉴스 접근이 되는지 점검
```

- `groups.org` 는 기관 이름 단어(`any`)가 제목·요약에 있으면, `groups.site` 는 지명(`place`)과 사업 단어(`with_any`)가 함께 있으면 해당한다. 둘 다면 "공통"
- `queries` 는 매일 도는 기본 검색어, `period_queries` 는 전체 수집 때만 기간을 잘라 과거분을 보강한다(RSS는 쿼리당 100건 상한)
- 주제 규칙은 앞선 것부터 적용한다. 어느 규칙에도 안 걸리면 "기타 동향"

## 수집 구조

1. 구글뉴스 RSS(한국어)로 검색어별 수집. 쿼리 사이 0.4초
2. 관련성 필터와 제목 앞 40자 기준 중복 제거
3. 원문 주소 복원. RSS 링크는 구글 경유 주소라 기사 페이지 정보로 실제 언론사 주소를 받아온다
4. 요약 추출. 원문의 `og:description`. 인코딩은 UTF-8 우선, 실패 시 CP949. 깨진 결과는 비운다
5. 주제 분류 후 `data/news.json` 과 허브용 `data/status.json` 기록

## 함정

- **수집 0건은 실패다.** 검색어 전부가 빈손이면 원본이 응답하지 않은 것이다. `build.py` 는 이때 `exit 2` 로 끝나고, `run_daily.sh` 는 스탬프를 남기지 않아 다음 깨움에 재시도한다. 0건이 "성공"으로 끝나면 며칠치 기사가 소리 없이 빠진다
- 조용한 실패 방지. 실행 결과는 `logs/daily.log`, 직전 빌드 출력은 `logs/last_build.txt` 에서 확인한다
- 데이터센터 IP(깃허브 액션 러너 등)에서는 구글뉴스가 빈 응답을 주는 경우가 있다. 국내 회선 PC에서 돌린다
- `.cache/items.json` 이 누적 아카이브다. 지우면 과거 기사를 다시 못 받을 수 있다. 백업해 둔다
- `data/news.json` 은 직접 고치지 않는다. 다음 빌드가 덮어쓴다
- 기사 제목·요약·링크는 각 언론사 저작권이다. 화면은 원문으로 가는 색인만 제공한다
