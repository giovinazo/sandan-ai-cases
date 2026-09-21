#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정보공개포털 원문공개 첨부 내려받기.

목록 수집(collect.py)과는 다른 경로다. 원문공개로 등재된 문서만 첨부를 받을 수 있고,
화면이 쓰는 6단계 ajax 체인을 그대로 따라야 한다.

  1) 상세 페이지 GET     -> 문서 VO(openCateSearchVO) + 파일 목록(fileId·fileNm)
  2) wonmunFileRequest   -> esbFilePath 확보
  3) wonmunFileFilter    -> 개인정보 필터링 통과 (error_code=01 이면 건너뛴다)
  4) wonmunFileDownload  -> 바이너리 수신

isPdf 는 항상 "N". 화면의 다운로드 단추도 N 으로 부른다("Y" 는 뷰어용 PDF 변환 경로).

사용법
  python3 download_orginl.py --list                 # 받을 수 있는 문서 목록
  python3 download_orginl.py <문서ID>               # 그 문서의 첨부 전부
  python3 download_orginl.py <문서ID> --files       # 첨부 목록만 보고 끝
  python3 download_orginl.py <문서ID> --only <fileId>  --out 어디에
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

from portal_client import BASE, UA, PortalClient

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "data", "documents.json")
OUTROOT = os.path.join(HERE, "downloads")

# 파일 사이 간격. 포털은 대량 호출에 민감하다
GAP = 2.0


class Downloader(PortalClient):
    def _ajax(self, path, param, referer):
        body = urllib.parse.urlencode(param, encoding="utf-8").encode()
        req = urllib.request.Request(BASE + path, data=body, headers={
            "User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
            "X-XSRF-TOKEN": self._token(), "Referer": BASE + referer,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        return json.loads(self._open(req).read().decode("utf-8"))

    def detail(self, rgst_no, prdn_dt, nst_se):
        """상세 페이지에서 문서 VO 와 파일 목록을 뽑는다.

        파일 목록은 별도 ajax 가 아니라 페이지 안에 흩어져 있어 정규식으로 훑는다.
        같은 fileId 가 여러 번 나오므로 중복을 걷어낸다.
        """
        q = urllib.parse.urlencode({"prdnNstRgstNo": rgst_no,
                                    "prdnDt": prdn_dt, "nstSeCd": nst_se})
        path = f"/othicInfo/infoList/infoListDetl.do?{q}"
        html = self._get(path).decode("utf-8", "replace")
        m = re.search(r'var\s+result\s*=\s*(\{"openCateSearchVO")', html)
        if not m:
            raise RuntimeError("상세 페이지에서 문서 정보를 찾지 못했다(비공개이거나 주소가 틀렸다)")
        vo = json.JSONDecoder().raw_decode(html[m.start(1):])[0]["openCateSearchVO"]
        seen, files = set(), []
        for f in re.finditer(r'"fileId":"([^"]+)".*?"fileNm":"([^"]*)"'
                             r'.*?"fileOrdr":"(\d+)","fileSeDc":"([^"]*)"', html):
            fid, nm, ordr, sec = f.groups()
            if fid in seen or not nm:
                continue
            seen.add(fid)
            files.append({"fileId": fid, "fileNm": nm, "ordr": int(ordr), "se": sec})
        files.sort(key=lambda x: (x["se"] != "본문", x["ordr"]))
        return vo, files, path

    def download(self, vo, f, referer, outdir):
        """파일 1건을 받아 저장한다. 실패하면 예외."""
        r1 = self._ajax("/util/wonmunUtils/wonmunFileRequest.ajax", {
            "fileId": f["fileId"], "esbFileName": f["fileNm"],
            "docId": vo["docNo"], "ctDate": vo["prdnDt"], "orgCd": vo["nstCd"],
            "prdnNstRgstNo": vo["prdnNstRgstNo"], "oppSeCd": vo["oppSeCd"],
            "isPdf": "N", "chrgDeptNm": vo["chrgDeptNm"]}, referer)
        if str(r1.get("code")) == "429":
            raise SystemExit("포털이 사람 확인(캡차)을 요구한다. 여기서 멈춘다.")
        code = str(r1.get("error_code"))
        if code not in ("0", "00", "01"):
            raise RuntimeError(f"요청 단계 실패 {code} {r1.get('error_msg')}")

        cur = r1
        if code in ("0", "00"):          # 01 은 필터링 없이 바로 받는다
            time.sleep(self.delay)
            cur = self._ajax("/util/wonmunUtils/wonmunFileFilter.ajax", {
                "prdnNstRgstNo": vo["prdnNstRgstNo"], "prdnDt": vo["prdnDt"],
                "esbFilePath": r1.get("esbFilePath", ""),
                "esbFileName": r1.get("esbFileName", ""),
                "fileName": r1.get("fileName", ""), "fileId": f["fileId"],
                "orglPrdnNstCd": r1.get("orglPrdnNstCd", ""), "nstCd": vo["nstCd"],
                "orgCd": vo["nstCd"], "orgSeCd": vo["nstSeCd"], "infoSj": vo["infoSj"],
                "chgrNmpn": vo["chgrNmpn"], "orgNm": vo["prcsNstNm"],
                "chrgDeptCd": vo["chrgDeptCd"], "chrgDeptNm": vo["chrgDeptNm"],
                "nstClNm": vo["nstClNm"], "prsrvPdCd": vo["prsrvPdCd"],
                "docId": vo["docNo"], "isPdf": r1.get("isPdf", "N"), "step": "step2",
                "closegvrnYn": r1.get("closegvrnYn", ""),
                "ndnfFiltrRndabtYn": vo.get("ndnfFiltrRndabtYn", ""),
                "rceptInsttCd": vo.get("rceptInsttCd", ""),
                "rceptInsttCdNm": vo.get("rceptInsttCdNm", ""),
                "mngrTelno": r1.get("mngrTelno", "")}, referer)
            if str(cur.get("error_code")) not in ("0", "00"):
                raise RuntimeError(f"필터링 단계 실패 {cur.get('error_code')} {cur.get('error_msg')}")

        time.sleep(self.delay)
        body = urllib.parse.urlencode({
            "esbFilePath": cur.get("esbFilePath", ""),
            "esbFileName": cur.get("esbFileName", ""),
            "fileName": cur.get("fileName", ""), "isPdf": cur.get("isPdf", "N"),
            "prdnNstRgstNo": vo["prdnNstRgstNo"], "prdnDt": vo["prdnDt"],
            "fileId": f["fileId"], "gubun": "esbFilePath"}, encoding="utf-8").encode()
        req = urllib.request.Request(BASE + "/util/wonmunUtils/wonmunFileDownload.down",
                                     data=body,
                                     headers={"User-Agent": UA, "Referer": BASE + referer})
        data = self._open(req).read()
        if len(data) < 2048 and b"html" in data[:400].lower():
            raise RuntimeError(f"파일 대신 HTML 을 받았다({len(data)}B). 공개구분을 확인할 것")
        path = os.path.join(outdir, f"{f['ordr']:02d}_{safe_name(f['fileNm'])}")
        with open(path, "wb") as fp:
            fp.write(data)
        return path, len(data)


def safe_name(s):
    return re.sub(r'[/:\\]', "_", s).strip()


def load_docs():
    if not os.path.exists(DOCS):
        raise SystemExit(f"수집 결과가 없다: {DOCS} (먼저 collect.py 를 돌릴 것)")
    return json.load(open(DOCS, encoding="utf-8"))


def find_doc(doc_id):
    """수집 결과에서 문서를 찾아 (id, 생산일시, 기관구분, 제목)을 돌려준다."""
    d = load_docs()
    for sec in ("orginl", "infolist"):
        for it in d["items"].get(sec, []):
            if it["id"] == doc_id:
                return it
    return None


def list_downloadable():
    """원문공개로 등재돼 첨부를 받을 수 있는 문서."""
    d = load_docs()
    seen, out = set(), []
    for sec in ("orginl", "infolist"):
        for it in d["items"].get(sec, []):
            if it["id"] in seen:
                continue
            if it.get("othbc") == "공개" and (it.get("file_nm") or it.get("has_orginl")):
                seen.add(it["id"])
                out.append(it)
    out.sort(key=lambda x: x.get("datetime", ""), reverse=True)
    return out


def main():
    ap = argparse.ArgumentParser(description="정보공개포털 원문공개 첨부 내려받기")
    ap.add_argument("doc_id", nargs="?", help="문서 ID(수집 결과의 id). --list 로 확인")
    ap.add_argument("--list", action="store_true", help="받을 수 있는 문서 목록만 보여준다")
    ap.add_argument("--files", action="store_true", help="첨부 목록만 보여주고 받지 않는다")
    ap.add_argument("--only", help="이 fileId 하나만 받는다")
    ap.add_argument("--out", help="저장 폴더(기본 downloads/<문서ID>_<제목>)")
    ap.add_argument("--prdn-dt", help="생산일시 14자리(수집 결과에 없는 문서를 직접 지정할 때)")
    ap.add_argument("--nst-se", help="기관구분 C/W/B/E/P (직접 지정할 때)")
    args = ap.parse_args()

    if args.list:
        rows = list_downloadable()
        print(f"원문공개 문서 {len(rows)}건\n")
        for it in rows:
            print(f"  {it['id']}  {it['date']}  [{it['instt']}] {it['title'][:60]}")
            n = len([x for x in (it.get('file_nm') or '').split('|') if x])
            if n:
                print(f"      첨부 {n}건")
        return

    if not args.doc_id:
        ap.error("문서 ID 를 지정하거나 --list 를 쓸 것")

    it = find_doc(args.doc_id)
    prdn_dt = args.prdn_dt or (it or {}).get("datetime")
    nst_se = args.nst_se or (it or {}).get("instt_se")
    if not (prdn_dt and nst_se):
        raise SystemExit("수집 결과에 없는 문서다. --prdn-dt 와 --nst-se 를 직접 줄 것")

    c = Downloader()
    c.prepare("orginl")
    vo, files, ref = c.detail(args.doc_id, prdn_dt, nst_se)
    print(f"문서 : {vo['infoSj']}")
    print(f"기관 : {vo['prcsNstNm']} / {vo['docNo']} / 공개구분 {vo['oppSeCd']}")
    print(f"파일 : {len(files)}건\n")
    for f in files:
        print(f"  [{f['se']}] {f['fileNm']}   ({f['fileId']})")
    if args.files:
        return
    if vo.get("oppSeCd") != "1":
        raise SystemExit("\n공개 문서가 아니다. 첨부를 받을 수 없다.")

    outdir = args.out or os.path.join(
        OUTROOT, f"{args.doc_id}_{safe_name(vo['infoSj'])[:40]}")
    os.makedirs(outdir, exist_ok=True)
    print(f"\n저장 : {outdir}\n")

    ok = 0
    for f in files:
        if args.only and f["fileId"] != args.only:
            continue
        try:
            _, n = c.download(vo, f, ref, outdir)
            print(f"  ✓ {f['se']:2s} {f['fileNm']}  →  {n:,}B")
            ok += 1
        except SystemExit:
            raise
        except Exception as e:
            print(f"  ✗ {f['se']:2s} {f['fileNm']}  →  {e}")
        time.sleep(GAP)
    print(f"\n{ok}건 저장 완료")


if __name__ == "__main__":
    sys.exit(main())
