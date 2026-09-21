#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정보공개포털(open.go.kr) 검색 클라이언트.

포털은 공개 API를 제공하지 않으므로 화면이 쓰는 ajax 엔드포인트를 그대로 호출한다.
호출 전 브라우저 지문 등록과 CSRF 토큰 세팅이 필요하다.
  1) 목록 페이지 GET  -> 세션·XSRF-TOKEN 쿠키 획득
  2) setFingerPrint.ajax POST -> 지문 등록 (생략 시 code 491로 거부)
  3) 검색 ajax POST (X-XSRF-TOKEN 헤더 필수)
"""

import hashlib
import http.cookiejar
import json
import ssl
import time
import urllib.parse
import urllib.request

BASE = "https://www.open.go.kr"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

KINDS = {
    "infolist": {
        "name": "정보목록",
        "ajax": "/othicInfo/infoList/infoList.ajax",
        "page": "/othicInfo/infoList/infoList.do",
        "detail": "/othicInfo/infoList/infoListDetl2.do",
    },
    "orginl": {
        "name": "원문공개",
        "ajax": "/othicInfo/infoList/orginlInfoList.ajax",
        "page": "/othicInfo/infoList/orginlInfoList.do",
        "detail": "/othicInfo/infoList/infoListDetl.do",
    },
}

INSTT_SE = {"C": "중앙행정기관", "W": "광역자치단체", "B": "기초자치단체",
            "E": "교육청", "P": "공공기관"}
OTHBC_SE = {"1": "공개", "2": "부분공개", "3": "비공개"}


class PortalError(RuntimeError):
    pass


class PortalClient:
    def __init__(self, timeout=40, delay=1.3):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE          # 포털 인증서 체인 이슈 회피
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=ctx),
        )
        self.timeout = timeout
        self.delay = delay
        self._ready_for = None

    # --- 내부 유틸 ---------------------------------------------------
    def _token(self):
        return next((c.value for c in self.cj if c.name == "XSRF-TOKEN"), "")

    def _open(self, req, retries=2):
        """포털이 이따금 응답 없이 연결을 끊는다. 몇 초 쉬고 다시 시도한다."""
        last = None
        for i in range(retries + 1):
            try:
                return self.op.open(req, timeout=self.timeout)
            except Exception as e:
                last = e
                if i < retries:
                    time.sleep(2 + i * 2)
        raise last

    def _get(self, path):
        req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
        return self._open(req).read()

    def _post(self, path, data, referer):
        body = urllib.parse.urlencode(data, encoding="utf-8").encode()
        headers = {
            "User-Agent": UA,
            "X-Requested-With": "XMLHttpRequest",
            "X-XSRF-TOKEN": self._token(),
            "Referer": BASE + referer,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        req = urllib.request.Request(BASE + path, data=body, headers=headers)
        raw = self._open(req).read().decode("utf-8")
        return json.loads(raw)

    # --- 세션 준비 ---------------------------------------------------
    def prepare(self, kind="infolist"):
        page = KINDS[kind]["page"]
        self._get(page)
        fp = hashlib.sha256(b"open-go-kr-monitor").hexdigest().upper()
        self._post("/common/util/setFingerPrint.ajax", {"fingerprint": fp}, page)
        self._ready_for = kind

    # --- 검색 --------------------------------------------------------
    def search(self, kind, kwd, start_date, end_date, page=1, rows=50,
               sort="s", instt_se="", othbc_se="", instt_cd=""):
        """한 페이지를 조회해 (전체건수, 레코드목록)을 돌려준다."""
        if self._ready_for is None:
            self.prepare(kind)
        meta = KINDS[kind]
        param = {
            "kwd": kwd, "preKwds": kwd, "reSrchFlag": "off", "srchFd": "",
            "startDate": start_date, "endDate": end_date,
            "viewPage": page, "rowPage": rows, "sort": sort,
            "insttSeCd": instt_se, "eduYn": "", "othbcSeCd": othbc_se,
            "insttCd": instt_cd, "insttCdNm": "",
        }
        res = self._post(meta["ajax"], param, meta["page"])["result"]
        code = str(res.get("code", ""))
        if code == "491":                      # 지문 만료 -> 1회 재수립
            self.prepare(kind)
            res = self._post(meta["ajax"], param, meta["page"])["result"]
            code = str(res.get("code", ""))
        if code != "200":
            raise PortalError(f"포털 응답코드 {code} (kind={kind}, kwd={kwd})")
        return int(res.get("rtnTotal") or 0), (res.get("rtnList") or [])

    def search_all(self, kind, kwd, start_date, end_date, rows=50,
                   max_pages=40, on_page=None):
        """페이지를 넘겨가며 전건을 모은다."""
        out, page = [], 1
        total, first = self.search(kind, kwd, start_date, end_date, 1, rows)
        out.extend(first)
        if on_page:
            on_page(kind, kwd, 1, total, len(first))
        while len(out) < total and page < max_pages:
            page += 1
            time.sleep(self.delay)
            _, rec = self.search(kind, kwd, start_date, end_date, page, rows)
            if not rec:
                break
            out.extend(rec)
            if on_page:
                on_page(kind, kwd, page, total, len(out))
        return total, out


def detail_url(kind, rec):
    """포털 상세화면 주소를 만든다."""
    q = urllib.parse.urlencode({
        "prdnNstRgstNo": rec.get("PRDCTN_INSTT_REGIST_NO", ""),
        "prdnDt": rec.get("PRDCTN_DT", ""),
        "nstSeCd": rec.get("INSTT_SE_CD", ""),
    })
    return f"{BASE}{KINDS[kind]['detail']}?{q}"


def normalize(kind, rec, hit_kwd):
    """포털 원본 레코드를 대시보드용 항목으로 정리한다."""
    dt = rec.get("PRDCTN_DT", "") or ""
    return {
        "id": rec.get("PRDCTN_INSTT_REGIST_NO", ""),
        "title": (rec.get("INFO_SJ") or "").strip(),
        "instt": (rec.get("PROC_INSTT_NM") or "").strip(),
        "instt_se": rec.get("INSTT_SE_CD", ""),
        "instt_se_nm": INSTT_SE.get(rec.get("INSTT_SE_CD", ""), ""),
        "dept": (rec.get("NFLST_CHRG_DEPT_NM") or rec.get("CHRG_DEPT_NM") or "").strip(),
        "doc_no": rec.get("DOC_NO", ""),
        "charger": rec.get("CHARGER_NM", ""),
        "unit_job": rec.get("UNIT_JOB_NM", ""),
        "date": f"{dt[0:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) >= 8 else "",
        "datetime": dt,
        "othbc": OTHBC_SE.get(rec.get("OTHBC_SE_CD", ""), ""),
        "file_nm": rec.get("FILE_NM", ""),
        "has_orginl": rec.get("ORGNAL_YN", "") == "Y",
        "url": detail_url(kind, rec),
        "kwds": [hit_kwd],
    }
