"""Settings from config.json, with environment overrides for local testing.

EDU_PORT=8000 EDU_DEV=1 python server.py   -> serves on localhost, accepts any Host header
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path=None):
    cfg = json.loads(Path(path or ROOT / "config.json").read_text(encoding="utf-8"))
    cfg["port"] = int(os.environ.get("EDU_PORT", cfg.get("port", 80)))
    cfg["dev"] = os.environ.get("EDU_DEV") == "1"
    if os.environ.get("EDU_DATA_DIR"):
        cfg["data_dir"] = os.environ["EDU_DATA_DIR"]
    for key in ("data_dir", "seed_dir", "answer_zone_path"):
        p = Path(cfg[key])
        cfg[key] = str(p if p.is_absolute() else ROOT / p)
    # answer_zone lives in the repo root (arduino/..) or, outside the repo, in a sibling clone
    for cand in (cfg["answer_zone_path"], ROOT.parent, ROOT.parent / "minimos-locales-qualcomm"):
        if (Path(cand) / "answer_zone").is_dir():
            cfg["answer_zone_path"] = str(cand)
            break
    return cfg
