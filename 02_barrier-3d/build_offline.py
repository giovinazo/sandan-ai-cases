#!/usr/bin/env python3
"""오프라인 단일 파일 빌드.

index.html + config.js + app.js + lib/three/* 를 하나의 HTML로 합칩니다.
결과 파일(barrier-review-offline.html)은 인터넷 없이 더블클릭으로 열립니다.

사용법:
    python3 build_offline.py            # 같은 폴더에 barrier-review-offline.html 생성
    python3 build_offline.py -o 출력.html

원리: 브라우저는 file:// 에서 ES 모듈 파일을 불러오지 못하므로, three.js 소스를
<script type="text/plain">에 넣고 실행 시 Blob URL로 바꿔 import map에 연결합니다.
표준 라이브러리만 씁니다.
"""
import argparse
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
LIB = HERE / "lib" / "three"


def read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


def guard(src: str, name: str) -> str:
    # 인라인 스크립트 안에 '</script'가 있으면 HTML 파싱이 끊기므로 확인
    if re.search(r"</script", src, re.I):
        sys.exit(f"오류: {name} 안에 </script 문자열이 있어 인라인할 수 없습니다.")
    return src


def build(out: pathlib.Path) -> None:
    html = read(HERE / "index.html")
    config = guard(read(HERE / "config.js"), "config.js")
    app = guard(read(HERE / "app.js"), "app.js")
    core = guard(read(LIB / "three.core.min.js"), "three.core.min.js")
    module = guard(read(LIB / "three.module.min.js"), "three.module.min.js")
    orbit = guard(read(LIB / "addons" / "controls" / "OrbitControls.js"), "OrbitControls.js")

    # 1) 설정: 파일 위쪽에 읽기 쉬운 블록으로 인라인 (이 블록만 고쳐도 됨)
    cfg_tag = '<script src="config.js"></script>'
    if cfg_tag not in html:
        sys.exit("오류: index.html에서 config.js 태그를 찾지 못했습니다.")
    cfg_block = (
        "<!-- ===== 설정(CONFIG): 자기 사업 수치는 아래 블록만 고치면 됩니다 ===== -->\n"
        f"<script>\n{config}</script>\n"
        "<!-- ===== 설정 끝 ===== -->"
    )

    # 2) import map → Blob URL 로더
    im = re.search(r'<script type="importmap">.*?</script>', html, re.S)
    if not im:
        sys.exit("오류: index.html에서 import map을 찾지 못했습니다.")
    loader = (
        "<!-- three.js r184 (MIT License, Copyright 2010-2026 three.js authors). lib/three/LICENSE 참조 -->\n"
        f'<script type="text/plain" id="src-three-core">{core}</script>\n'
        f'<script type="text/plain" id="src-three-module">{module}</script>\n'
        f'<script type="text/plain" id="src-orbit">{orbit}</script>\n'
        "<script>\n(function(){\n"
        "  var T=function(id){return document.getElementById(id).textContent;};\n"
        '  var U=function(s){return URL.createObjectURL(new Blob([s],{type:"text/javascript"}));};\n'
        '  var coreU=U(T("src-three-core"));\n'
        '  var modU=U(T("src-three-module").split("./three.core.min.js").join(coreU));\n'
        '  var orbU=U(T("src-orbit"));\n'
        "  document.write('<script type=\"importmap\">'+JSON.stringify({imports:{\"three\":modU,"
        "\"three/addons/controls/OrbitControls.js\":orbU}})+'<\\/script>');\n"
        "})();\n</script>"
    )

    # 3) 앱 모듈 인라인
    app_tag = '<script type="module" src="app.js"></script>'
    if app_tag not in html:
        sys.exit("오류: index.html에서 app.js 태그를 찾지 못했습니다.")

    html = html.replace(cfg_tag, cfg_block, 1)
    im = re.search(r'<script type="importmap">.*?</script>', html, re.S)
    html = html[: im.start()] + loader + html[im.end():]
    html = html.replace(app_tag, f'<script type="module">\n{app}</script>', 1)
    html = html.replace("<title>방음벽 폐쇄감 검토 모델</title>",
                        "<title>방음벽 폐쇄감 검토 모델 (오프라인판)</title>", 1)
    html = re.sub(r"<!--\n  읽기 쉬운 소스판입니다\..*?-->\n",
                  "<!-- build_offline.py로 만든 단일 파일입니다. 소스는 index.html · config.js · app.js -->\n",
                  html, count=1, flags=re.S)
    out.write_text(html, encoding="utf-8")
    print(f"생성: {out.name} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="오프라인 단일 HTML 빌드")
    ap.add_argument("-o", "--out", default=str(HERE / "barrier-review-offline.html"))
    build(pathlib.Path(ap.parse_args().out))
