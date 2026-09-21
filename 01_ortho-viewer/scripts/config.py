"""설정 파일(config.json) 읽기

  ㅇ 찾는 순서: 명령행 `--config 경로` > 환경변수 ORTHO_CONFIG > `../config.json`(이 폴더 위)
  ㅇ 설정 안의 상대경로는 **설정 파일이 있는 폴더 기준**으로 푼다
  ㅇ 셸 스크립트에서 값을 꺼낼 때:  python3 config.py get source.dsm --config 경로

사업마다 달라지는 값(원본 파일 경로, 자르는 범위, 제목, 배율)은 모두 설정 파일에 둔다.
코드에는 사업 고유 수치를 적지 않는다.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEFAULTS = {
    "title": "현황지도",
    "subtitle": "정사영상 · 음영기복 · 측정",
    "footer": "업무 참고용",
    "crs": {"epsg": 5186, "lat0": 38.0, "lon0": 127.0, "k0": 1.0, "fe": 200000.0, "fn": 600000.0},
    "source": {"ortho": None, "dsm": None, "ground": None, "dxf_dir": None, "nodata": -10000},
    "crop_box": None,
    "ortho_zoom": [14, 22],
    "hs_zoom": [14, 20],
    "hs_z_factor": 4,
    "grid_res_m": 2.3873,
    "data_dir": "vectors",
    "output_dir": "output",
    "work_dir": "output/work",
    "view_3d": {"tex_zoom": 19, "step": 8, "max_side": 6144, "jpeg_quality": 82},
    "labels": {"surface_note": "표면 = DSM(나무·건물 지붕 포함)",
               "ground_note": "지반 = 지면 표고",
               "cadastral_note": ""},
}

PATH_KEYS = [("source", "ortho"), ("source", "dsm"), ("source", "ground"), ("source", "dxf_dir"),
             ("data_dir",), ("output_dir",), ("work_dir",)]


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def find_path(argv=None):
    argv = sys.argv if argv is None else argv
    if "--config" in argv:
        i = argv.index("--config")
        if i + 1 < len(argv):
            return os.path.abspath(argv[i + 1])
    env = os.environ.get("ORTHO_CONFIG")
    if env:
        return os.path.abspath(env)
    return os.path.join(ROOT, "config.json")


def load(argv=None):
    path = find_path(argv)
    if not os.path.exists(path):
        sys.exit(f"설정 파일이 없습니다: {path}\n"
                 f"  config.example.json 을 config.json 으로 복사해 고치거나,\n"
                 f"  --config sample_data/config.json 처럼 지정하십시오")
    cfg = _merge(DEFAULTS, json.load(open(path, encoding="utf-8")))
    base = os.path.dirname(path)
    for keys in PATH_KEYS:
        d = cfg
        for k in keys[:-1]:
            d = d[k]
        v = d.get(keys[-1])
        if v:
            d[keys[-1]] = os.path.normpath(os.path.join(base, os.path.expanduser(v)))
    cfg["_path"] = path
    return cfg


def get(cfg, dotted):
    v = cfg
    for k in dotted.split("."):
        v = v[k]
    return v


if __name__ == "__main__":
    # 셸에서 값 꺼내기: python3 config.py get crop_box --config 경로
    if len(sys.argv) >= 3 and sys.argv[1] == "get":
        v = get(load(), sys.argv[2])
        if isinstance(v, (list, tuple)):
            print(" ".join(str(x) for x in v))
        elif v is None:
            print("")
        else:
            print(v)
    else:
        print(json.dumps(load(), ensure_ascii=False, indent=2))
