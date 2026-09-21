# 허브(hub)

감시 화면들로 들어가는 진입 화면. 각 화면이 배포해 둔 `status.json`(수백 바이트)만 읽어 타일에 대표 수치와 갱신 시각을 띄운다. 본 데이터는 받지 않는다.

## 구성

| 파일 | 역할 |
|---|---|
| `index.html` | 화면 뼈대 |
| `assets/sites.js` | **사이트 목록 설정.** 제목, 타일별 주소·status 주소·대표 지표 |
| `assets/app.js` | status.json 을 받아 타일 채우기, 지연 판정 |
| `assets/stars.js`, `assets/style.css` | 배경 입자와 흑백 스타일 |
| `sample_data/*.status.json` | 가상 예시 요약(세 도구의 예시 빌드 결과와 같은 값) |
| `vercel.json`, `robots.txt` | 배포 설정(검색엔진 차단) |

## 준비물

- 없음(정적 파일). 로컬 확인에만 파이썬 내장 웹서버를 쓴다

## 예시로 돌려보기

```bash
python3 -m http.server 8000
# http://127.0.0.1:8000/?sample
```

주소에 `?sample` 을 붙이면 `sample_data/` 의 예시 요약을 읽는다. 붙이지 않으면 `sites.js` 의 실제 status 주소를 읽는다(예시 주소는 example.com 이라 숫자 자리가 빈 표시로 남는다). fetch 를 쓰므로 파일을 바로 열지 말고 웹서버로 연다.

## 자기 설정으로 바꾸기

`assets/sites.js` 의 `sites` 를 고친다.

| 항목 | 뜻 |
|---|---|
| `url` | 타일을 눌렀을 때 여는 화면 주소 |
| `status` | 그 화면의 status.json 주소 |
| `pick` | metrics 중 타일에 띄울 항목의 label |
| `staleHours` | 이 시간보다 오래되면 "지연"으로 센다. 도구의 갱신 주기에 맞춘다 |
| `fixed` | 수집물이 아닌 고정값 타일(`{value, unit}`), 이때 `status` 는 `null` |

status.json 스키마: `{"key","title","updated","metrics":[{"label","value","unit"}]}`. 이 형식만 맞추면 어떤 도구든 타일로 붙일 수 있다.

## 함정

- 다른 주소의 status.json 을 읽으므로 각 화면이 CORS 를 허용해야 한다. 이 묶음의 `vercel.json` 에는 넣어 두었다. 다른 호스팅은 `Access-Control-Allow-Origin` 헤더를 확인한다
- 상단의 "지연 N" 은 수집이 멈췄다는 신호다. 숫자가 그대로여도 갱신 시각이 멈췄는지 본다(타일에 마우스를 올리면 기준 시각이 보인다)
- status.json 을 못 받아도 타일과 링크는 뜬다. 숫자 자리가 비어 있으면 주소·CORS·배포 상태를 확인한다
