# 사례 4. 공개정보 감시(OSINT) 모니터링

사업 관련 공개정보를 매일 자동으로 모아 한 화면에서 보는 도구 묶음. 정보공개포털 문서목록, 언론보도, 공식 계정 공개 게시물을 각각 수집해 정적 웹 화면으로 만들고, 허브 화면이 세 화면의 요약 수치만 모아 보여준다.

모든 도구에 가상 예시자료(`sample_data/`)가 들어 있어 네트워크 없이 화면을 바로 확인할 수 있다. 예시의 기관·기사·게시물은 모두 지어낸 것이다.

## 구성

| 폴더 | 무엇 | 수집원 | 화면 |
|---|---|---|---|
| `portal-monitor/` | 정보공개포털 감시 | 정보공개포털(open.go.kr) 정보목록·원문공개 | `index.html` + `data.js` |
| `newsboard/` | 뉴스 대시보드 | 구글뉴스 RSS(한국어) | `index.html` + `data/news.json` |
| `sns-monitor/` | SNS 모아보기 | 공식 계정의 공개 RSS·Atom 피드 | `web/` |
| `hub/` | 허브(진입 화면) | 세 화면의 `status.json` | `index.html` |
| `automation/` | 매일 자동 실행 예시 | cron·launchd 틀 | |

## 관계도

```
 [정보공개포털]      [구글뉴스 RSS]       [공개 피드]
       │                  │                   │
  collect.py          build.py            collect.py
       │                  │                   │
  build_web.py            │               build_web.py
       │                  │                   │
  data.js             data/news.json      web/data.js        ← 각 화면이 읽는 본 데이터(수백 KB)
  status.json         data/status.json    web/data/status.json  ← 요약(수백 바이트)
       │                  │                   │
       └──────────────────┼───────────────────┘
                          │  status.json 만 fetch
                        [허브]
```

## 허브가 status.json 만 읽는 구조

각 도구는 빌드 때 본 데이터와 함께 요약 파일 `status.json` 을 만든다. 스키마는 네 도구가 같다.

```json
{"key": "portal", "title": "정보공개포털 모니터링", "updated": "2026-09-21T07:00:00+09:00",
 "metrics": [{"label": "수집 문서", "value": 22, "unit": "건"}]}
```

- 허브는 이 파일만 받아 타일 숫자를 채운다. 본 데이터(수백 KB)를 허브에서 통째로 받지 않는다
- `updated` 가 정한 시간(`staleHours`)보다 오래되면 허브 상단에 "지연"으로 센다. 수집이 멈춘 것을 한눈에 알아채는 장치
- 못 받아도 타일과 링크는 그대로 뜬다
- 새 도구를 붙일 때는 같은 스키마의 `status.json` 만 만들면 된다

## 예시로 돌려보기(네트워크 불필요)

Python 3.9 이상. 설치할 패키지 없음(표준 라이브러리만).

```bash
cd 04_osint-monitor
python3 portal-monitor/build_web.py --sample --mask
python3 newsboard/build.py --sample
python3 sns-monitor/build_web.py --sample
python3 -m http.server 8000
```

브라우저에서 확인.

- http://127.0.0.1:8000/portal-monitor/
- http://127.0.0.1:8000/newsboard/
- http://127.0.0.1:8000/sns-monitor/web/
- http://127.0.0.1:8000/hub/?sample (허브는 `?sample` 을 붙이면 `hub/sample_data/` 의 예시 요약을 읽는다)

생성 산출물(`data.js`, `data/`, `status.json` 등)은 `.gitignore` 에 들어 있다.

## 자기 설정으로 바꾸기

실제 수집 대상은 예시 설정(`*.example.json`)을 복사해 고친다. 복사본(`config.json`, `targets.json`, `keywords.json`)은 `.gitignore` 에 들어 있어 공개 저장소에 올라가지 않는다.

| 도구 | 예시 설정 | 고칠 것 |
|---|---|---|
| portal-monitor | `config.example.json` | 검색어, 분류 규칙(사업 직결·부지·제외), 화면 제목 |
| newsboard | `config.example.json` | 검색어, 그룹(기관·사업지) 판정 단어, 주제 규칙 |
| sns-monitor | `targets.example.json`, `keywords.example.json` | 공식 계정 피드 주소, 관심 키워드 그룹 |
| hub | `assets/sites.js` | 각 화면 배포 주소와 status.json 주소 |

자세한 방법은 각 폴더의 README 참고.

## 매일 자동 실행

각 도구의 실행 스크립트(`run_daily.sh`, `run.sh`)에 "오늘 이미 끝났으면 즉시 종료" 가드가 있다. 스케줄러는 15~30분마다 깨우기만 하고, 하루 1회 판정은 스크립트가 한다. PC가 아침에 늦게 켜져도 켜진 뒤 첫 깨움에 돈다.

- cron(리눅스·맥): `automation/crontab.example`
- launchd(맥): `automation/com.example.osint-portal.plist`
- 윈도우: 작업 스케줄러에 같은 명령을 등록(WSL 또는 Git Bash에서 zsh·bash 실행)

스케줄러 환경의 함정

- PATH·로케일이 거의 비어 있다. 파이썬·git·curl 은 절대경로로 부르고 `LANG` 을 지정한다
- 경로에 한글이 있으면 실패하는 경우가 있다. 작업본은 영문 경로에 둔다
- 클라우드 동기화 폴더는 macOS 보호로 스케줄러가 못 여는 경우가 있다. 홈 아래 일반 폴더에 둔다
- 해외 데이터센터 IP(깃허브 액션 러너 등)는 정보공개포털이 막거나 구글뉴스가 빈 응답을 주는 경우가 있다. 국내 회선 PC에서 돌리는 편이 안정적이다

## 배포(정적 호스팅)

네 화면 모두 서버가 필요 없는 정적 파일이다. Vercel·Netlify·GitHub Pages 등 어디든 올릴 수 있다.

- 도구마다 배포 폴더가 다르다. `portal-monitor/`, `newsboard/`, `sns-monitor/web/`, `hub/`
- 각 폴더의 `.vercelignore` 가 수집 코드·설정·예시자료를 배포에서 뺀다
- Vercel CLI 예: 배포 폴더에서 `vercel deploy --prod`. 배포 뒤 받은 주소(예: 배포 주소)를 `hub/assets/sites.js` 에 적는다
- 이 저장소는 생성 산출물을 `.gitignore` 로 뺀다. 깃 연동 자동 배포를 쓰려면 자기 비공개 배포 저장소에서 `data.js`·`data/`·`status.json` 줄을 `.gitignore` 에서 지운다. 수집 원본(`portal-monitor/data/`)은 담당자 성명이 있으므로 계속 제외한다
- 다른 주소의 허브가 `status.json` 을 읽을 수 있도록 `vercel.json` 에 CORS 허용 헤더를 넣어 두었다

## 수집 예절(원칙)

- 공개된 화면·피드만 수집한다. 로그인이 필요한 화면, 비공개 글은 대상이 아니다
- 요청 간격을 둔다. 정보공개포털 1.3초, SNS 피드 2.5초, 원문 첨부 내려받기 파일 사이 2초. 간격을 줄이지 않는다
- 차단 징후(응답코드 429, 사람 확인 요구)가 보이면 즉시 멈춘다. 재시도를 반복하면 차단 등급이 올라간다
- SNS 수집기는 robots.txt 가 막은 주소를 건너뛴다
- 검색엔진 등록을 막는다. 모든 화면에 `<meta name="robots" content="noindex">`, `robots.txt`(Disallow), 응답 헤더 `X-Robots-Tag` 를 둔다
- 전문을 옮기지 않는다. 뉴스는 제목·요약(원문 메타정보)·링크만, SNS 는 요지·링크만 담아 원문으로 가는 색인 역할만 한다

## 유의사항

- 수집 결과에 개인정보가 섞일 수 있다. 정보공개포털 목록에는 담당자 성명이 있어 배포본은 `--mask` 로 성만 남긴다. 원본(`data/`)은 공개 저장소에 올리지 않는다
- 기사 제목·요약은 각 언론사 저작권이다. 화면은 내부 업무 참고용 색인으로 쓴다
- SNS 는 각 서비스 이용약관을 지킨다. 로그인 세션·쿠키를 재사용하는 수집 코드는 이 저장소에 넣지 않았다. 다른 수집원이 필요하면 `sns-monitor/sources/` 틀에 약관이 허용하는 방식(공식 API 등)으로 각자 책임 하에 구현한다
- 조용한 실패에 주의한다. 수집이 0건인데 "성공"으로 끝나면 며칠치가 소리 없이 빠진다. 실행 스크립트는 실패·0건일 때 스탬프를 남기지 않고 다음 깨움에 재시도하며, 결과는 `logs/daily.log` 에 남는다. 로그와 허브의 "지연" 표시를 주기적으로 확인한다
