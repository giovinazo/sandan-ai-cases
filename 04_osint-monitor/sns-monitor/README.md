# SNS 모아보기(sns-monitor)

기관·공인 공식 계정의 **공개 게시물**을 한 화면에 모으고, 관심 키워드가 들어간 글을 감지해 위로 올린다. 게시물의 요지·날짜·원문 링크만 담는다.

## 원칙

- **공개 게시물만.** 로그인 없이 누구나 열람할 수 있는 공식 계정의 공개 피드(RSS·Atom)만 수집한다
- 로그인 세션·쿠키·비밀번호를 쓰는 수집 코드와 로그인 상태 파일은 이 저장소에 넣지 않는다
- 각 서비스 **이용약관을 지킨다.** 피드가 없는 서비스는 공식 API 등 약관이 허용하는 방식으로 `sources/` 틀에 **각자 책임 하에** 구현한다
- robots.txt 가 막은 주소는 건너뛰고, 요청 사이 2.5초 간격을 둔다
- 비공개·친구공개 글, 댓글과 댓글 작성자 정보는 모으지 않는다

## 구성

| 파일 | 역할 |
|---|---|
| `collect.py` | 수집기. `rss`·`blog`·`youtube` 는 공개 피드를 읽고, `custom` 은 `sources/` 모듈을 부른다 |
| `sources/example_source.py` | 사용자 구현 수집원의 틀(기본값은 빈 목록) |
| `sns_common.py` | 같은 글 판정(주소 또는 계정+본문 앞 60자)과 한국어 시각 표기 해석 |
| `build_web.py` | 키워드 분류 후 `web/data.js`, 허브용 `web/data/status.json` 생성 |
| `dedupe_store.py` | 누적 저장소 정리(같은 글 합치기, 날짜 교정). 원본은 `backup/` 에 복사 |
| `targets.example.json` | 대상 계정 예시(가상 계정, 주소는 example.com) |
| `keywords.example.json` | 관심 키워드 그룹 예시 |
| `sample_data/posts.json` | 가상 예시자료 |
| `web/` | 화면(배포 폴더). `vercel.json`, `robots.txt` 포함 |
| `run.sh` | 일일 갱신 예시(수집 → 빌드 → 신규 있을 때만 배포) |

## 준비물

- Python 3.9 이상(표준 라이브러리만 사용)

## 예시로 돌려보기

```bash
python3 build_web.py --sample    # sample_data -> web/data.js, web/data/status.json
open web/index.html              # 파일을 바로 열어도 보인다(data.js 방식)
```

예시 빌드 결과: 게시물 11건, 키워드 감지 8건, 우선(사업 직결) 4건.

## 자기 설정으로 바꾸기

```bash
cp targets.example.json targets.json     # 깃 제외
cp keywords.example.json keywords.json   # 깃 제외
python3 collect.py --dry-run             # 저장하지 않고 수집 결과만 확인
python3 collect.py                       # data/posts.json 에 누적
python3 build_web.py
```

- `targets.json` 의 `accounts` 에 계정마다 `name`·`role`·`platform`·`feed`(공개 피드 주소)를 적는다. 적은 순서가 화면의 계정 필터 순서가 된다
- 공개 피드 주소 예: 기관 홈페이지 보도자료 RSS, 블로그 RSS, 유튜브 채널 피드(`https://www.youtube.com/feeds/videos.xml?channel_id=<채널ID>`)
- `site` 에 화면 제목과 허브 주소(`hub_url`)를 적는다
- `keywords.json` 의 `priority_groups` 에 든 그룹에 걸린 글은 상단에 고정된다

## 사용자 구현 수집원(custom)

`targets.json` 에 `"platform": "custom", "module": "sources.내모듈"` 로 적고 `sources/내모듈.py` 에 `fetch(account)` 를 만든다. 반환 형식은 `sources/example_source.py` 설명 참고. `sources/` 아래 개인 모듈은 `.gitignore` 로 빠진다.

- 해당 서비스 약관이 허용하는 방식만 쓴다
- API 키는 환경변수로 받고 키 파일은 저장소에 두지 않는다
- 로그인이 필요한 화면을 자동으로 긁는 방식은 약관 위반 소지가 크다. 쓰지 않는다

## 함정

- **새 글 0건인 날이 흔하다.** 공식 계정은 며칠씩 조용하다. `run.sh` 는 신규가 없으면 배포만 건너뛰고 정상 종료한다
- 조용한 실패 방지. 모든 대상이 실패하면 `collect.py` 가 `exit 2` 로 끝나고 `run.sh` 는 배포하지 않는다. 결과는 `logs/daily.log`, 직전 수집 출력은 `logs/last_collect.txt` 에서 확인한다
- 피드 주소는 기관 개편 때 바뀐다. 로그에 특정 계정만 계속 "실패"가 찍히면 주소를 다시 확인한다
- 날짜는 KST 기준으로 바꿔 저장한다. UTC 그대로 두면 새벽 글이 하루 밀린다
