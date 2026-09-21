# -*- coding: utf-8 -*-
"""설정 적재. 사업 고유 값(기관명·부서명·쪽 번호·열 경계 등)은 전부 config/project.json에 있다.

다른 설정 파일을 쓰려면 환경변수 OPINION_CONFIG에 경로를 준다.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]                 # 03_opinion-ledger
CONFIG = Path(os.environ.get("OPINION_CONFIG", ROOT / "config" / "project.json"))

C = json.load(open(CONFIG, encoding="utf-8"))
P = C["parser"]
N = C["names"]
GROUPS = C["groups"]
GROUP_NAMES = [g["name"] for g in GROUPS]
ROLE = {g["name"]: g["role"] for g in GROUPS}              # 기관군 → central/province/city/agency


def path(key):
    """paths.<key> → 절대경로(없으면 None)"""
    v = C["paths"].get(key)
    return (ROOT / v) if v else None


WORK = path("work_dir")
OUT = path("out_dir")
WORK.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)


def work(name):
    """중간 산출(JSON) 경로"""
    return WORK / name


def out(key):
    """최종 산출 경로(output_names.<key>)"""
    return OUT / C["output_names"][key]


def groups_of(role):
    return [g["name"] for g in GROUPS if g["role"] == role]
