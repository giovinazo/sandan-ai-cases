# -*- coding: utf-8 -*-
"""사용자 구현 수집원(custom)의 틀.

targets.json 의 계정에 "platform": "custom", "module": "sources.example_source" 로 적으면
collect.py 가 이 모듈의 fetch(account) 를 부른다.

지켜야 할 것(각자 책임 하에 설정)
  - 해당 서비스 이용약관이 허용하는 방식만 쓴다(공식 API, 공개 RSS 등)
  - 로그인 세션·쿠키·비밀번호를 코드나 저장소에 넣지 않는다
  - API 키가 필요하면 환경변수로 받고, 키 파일은 .gitignore 에 둔다
  - 공개 게시물만 대상으로 한다. 비공개·친구공개 글, 댓글 작성자 정보는 모으지 않는다
  - 요청 간격을 두고, robots.txt 를 따른다

반환 형식(게시물 하나)
  {"platform": "custom", "account": "계정 식별자", "author": "표시 이름", "role": "직함·구분",
   "text": "본문 요지(400자 이내 권장)", "date": "YYYY-MM-DD", "iso": "ISO 시각 또는 빈 문자열",
   "exact": True, "url": "원문 주소"}
"""


def fetch(account):
    # 여기에 약관이 허용하는 방식의 수집 코드를 넣는다. 기본값은 빈 목록.
    return []
