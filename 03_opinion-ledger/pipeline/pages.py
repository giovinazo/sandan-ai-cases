# -*- coding: utf-8 -*-
"""원본 PDF의 논리 쪽 목록.

한컴에서 A4 두 쪽을 가로 한 장에 모아찍어 보내는 경우가 있다(예: 1190×841pt).
장 너비가 기준값(parser.two_up_min_width)보다 넓으면 page.crop으로 좌·우 반을 갈라
논리 쪽 목록을 만든다. 잘린 반쪽의 괘선·글자 좌표는 한 쪽짜리 원본과 같은 방식으로 읽힌다.
한 쪽짜리 PDF는 그대로 통과한다. 쪽 번호는 왼쪽 반이 홀수, 오른쪽 반이 짝수.
"""
import pdfplumber

import cfg

TWO_UP_MIN_WIDTH = float(cfg.P.get("two_up_min_width", 1000.0))


def logical_pages(pdf_path):
    p = pdfplumber.open(pdf_path)
    out = []
    for pg in p.pages:
        if pg.width > TWO_UP_MIN_WIDTH:
            half = pg.width / 2
            out.append(pg.crop((0, 0, half, pg.height), relative=False))
            out.append(pg.crop((half, 0, pg.width, pg.height), relative=False))
        else:
            out.append(pg)
    return out
