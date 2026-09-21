# 정보공개포털 감시(portal-monitor)

정보공개포털(open.go.kr)에서 관심 사업 관련 문서목록을 검색어로 모아 대시보드로 보여준다. 정보공개목록(기관이 보유한 문서의 목록)과 원문공개목록(결재문서 원문이 공개된 건)을 나눠 담고, 제목 규칙으로 "사업 직결·부지·기타"를 가른다.

## 구성

| 파일 | 역할 |
|---|---|
| `index.html` | 대시보드 화면(필터·검색·CSV 내려받기). `data.js` 를 읽는다 |
| `portal_client.py` | 포털 세션·지문 등록·검색 처리 |
| `collect.py` | 수집기. 무옵션은 최근 45일 누적, `--full` 은 전체 이력 |
| `build_web.py` | 수집 결과를 화면용 `data.js` 와 허브용 `status.json` 으로 변환 |
| `reclassify.py` | 재수집 없이 분류 규칙만 다시 적용 |
| `download_orginl.py` | 원문공개 문서의 첨부 파일 내려받기 |
| `config.example.json` | 검색어·분류 규칙·화면 제목 예시 |
| `sample_data/documents.json` | 가상 예시자료(지어낸 기관·문서) |
| `run_daily.sh` | 매일 자동 실행 예시 |
| `vercel.json`, `.vercelignore`, `robots.txt` | 배포 설정(검색엔진 차단 포함) |

## 준비물

- Python 3.9 이상(표준 라이브러리만 사용, `requirements.txt` 참고)
- 실제 수집 시 국내 회선 인터넷

## 예시로 돌려보기

```bash
python3 build_web.py --sample --mask   # sample_data -> data.js, status.json
open index.html                        # 파일을 바로 열어도 보인다(data.js 방식)
```

예시 빌드 결과: 정보목록 22건, 원문공개 4건.

## 자기 설정으로 바꾸기

```bash
cp config.example.json config.json   # config.json 은 깃 제외
# config.json 의 keywords·classify·site 를 고친다
python3 collect.py --full            # 처음 1회 전체 이력(검색어 수에 따라 수 분)
python3 build_web.py --mask          # 배포본은 담당자 성명을 가린다
```

- 검색어는 "입력한 모든 단어가 제목에 포함(allword)" 방식이다. 단어를 많이 넣을수록 좁아진다
- 분류 규칙 하나는 단어 목록이고, 목록의 단어가 모두 제목(+단위업무)에 있으면 해당한다. 판정 순서는 강제 제외 → 제외(보호어가 있으면 구제) → 부지 → 사업 직결 → 기타
- 규칙만 바꿨으면 `python3 reclassify.py` 후 `build_web.py`. 재수집 불필요
- 검색어를 추가했으면 `collect.py --full` 로 과거분까지 다시 훑는다

## 원문공개 첨부 내려받기

```bash
python3 download_orginl.py --list              # 받을 수 있는 문서 목록
python3 download_orginl.py <문서ID> --files    # 첨부 목록만 확인
python3 download_orginl.py <문서ID>            # 첨부 전부 내려받기(downloads/)
```

- 공개구분이 "공개"인 원문공개 문서만 받을 수 있다
- 화면이 쓰는 절차(상세 → 요청 → 개인정보 필터 → 내려받기)를 그대로 따른다. 단계 사이 1.3초, 파일 사이 2초
- 응답코드 429(사람 확인 요구)가 오면 즉시 멈춘다. 재시도하지 않는다

## 매일 자동 실행

`run_daily.sh` 의 `DIR`·`PY` 를 고치고 cron·launchd 에 등록한다(상위 폴더 `automation/` 예시). 포털 접속 확인 → 수집 → 화면 데이터 → (깃을 쓰면) 커밋·푸시 순서로 돌고, 결과는 `logs/daily.log` 에 남는다.

## 함정

- **신규 0건 연속이 정상이다.** 사업 관련 문서는 며칠씩 안 나오는 게 보통이다. 0건 자체를 실패로 보지 말고, 로그의 "수집 시작·완료" 줄과 검색어별 "전체 N건" 줄이 매일 찍히는지로 판단한다
- 조용한 실패 방지. 실행 결과는 `logs/daily.log` 에서 확인한다. 스크립트는 수집 실패 시 스탬프를 남기지 않아 다음 깨움에 재시도한다. 파이프(`| tail`)로 이으면 종료코드를 놓치므로 파일로 받은 뒤 판정하게 되어 있다
- 포털은 공개 API가 없다. 화면이 쓰는 ajax 를 부르며 지문 등록과 CSRF 토큰이 필요하다. 포털 화면이 바뀌면 `portal_client.py` 를 손봐야 한다
- 요청 간격 1.3초를 줄이지 않는다. 차단될 수 있다
- 해외 데이터센터 IP(깃허브 액션 러너 등)는 포털이 막는 경우가 있다. 국내 회선 PC에서 돌린다
- 검색은 문서 **제목** 기준이다. 제목에 사업명이 없으면 잡히지 않는다
- 기관의 포털 등록에 시차가 있다. 생산일자와 등록일자가 수개월 벌어지기도 해서 최근 45일을 매번 다시 훑는다
- 제외어는 법인 표기까지 붙여 지정한다. `OO산업` 으로 쓰면 `OO산업단지` 까지 함께 걸린다
- 수집 원본 `data/documents.json` 에는 담당자 실명이 있다. 공개 저장소에 올리지 않는다(`.gitignore`). 배포본은 `--mask` 로 성만 남긴다
