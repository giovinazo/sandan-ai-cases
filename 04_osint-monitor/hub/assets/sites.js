/* 허브에 띄울 사이트 목록. 자기 배포 주소로 바꾼다.
   - url     타일을 눌렀을 때 여는 주소
   - status  그 사이트가 배포해 둔 status.json 주소(요약 스키마)
             {"key","title","updated","metrics":[{"label","value","unit"}]}
   - sample  ?sample 로 열었을 때 대신 읽는 로컬 예시 파일(네트워크 없이 화면 확인용)
   - pick    metrics 중 타일에 띄울 항목의 label. 없으면 첫 항목
   - staleHours  이 시간보다 오래되면 '지연'으로 센다
   - fixed   수집물이 아닌 고정값 타일이면 status 대신 {value, unit}
   아래 example.com 주소는 자리표시다. */
window.HUB_CONFIG = {
  title: "오픈소스 인텔리전스",
  eyebrow: "OO 산업단지",
  wordmark: "OO INDUSTRIAL COMPLEX",
  footer: "정보공개포털 · 언론보도 · 공개 SNS",
  sites: [
    { no: "01", key: "portal", cap: "DISCLOSURE PORTAL", name: "정보공개포털",
      url: "https://portal.example.com/",
      status: "https://portal.example.com/status.json",
      sample: "sample_data/portal.status.json",
      pick: "수집 문서", staleHours: 36 },
    { no: "02", key: "news", cap: "PRESS", name: "뉴스 스크랩",
      url: "https://news.example.com/",
      status: "https://news.example.com/data/status.json",
      sample: "sample_data/news.status.json",
      pick: "전체 기사", staleHours: 96 },
    { no: "03", key: "sns", cap: "PUBLIC SNS", name: "정책·현안 SNS",
      url: "https://sns.example.com/",
      status: "https://sns.example.com/data/status.json",
      sample: "sample_data/sns.status.json",
      pick: "키워드 감지", staleHours: 48 }
    /* 고정값 타일 예시
    ,{ no: "04", key: "map", cap: "SITE MAP", name: "현황 지도",
      url: "https://map.example.com/", status: null,
      fixed: { value: 120, unit: "필지" } } */
  ]
};
