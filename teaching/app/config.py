"""Settings from config.json, with environment overrides for local testing.

EDU_PORT=8000 EDU_DEV=1 python server.py   -> serves on localhost, accepts any Host header
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path=None):
    cfg = json.loads(Path(path or ROOT / "config.json").read_text(encoding="utf-8"))
    cfg["port"] = int(os.environ.get("EDU_PORT", cfg.get("port", 80)))
    cfg["dev"] = os.environ.get("EDU_DEV") == "1"
    if os.environ.get("EDU_DATA_DIR"):
        cfg["data_dir"] = os.environ["EDU_DATA_DIR"]
    cfg.setdefault("ocr_handoff_path", "ocr_handoff")     # the team's OCR pipeline (app/figures.py)
    cfg.setdefault("vendor_path", "vendor")               # extra wheels installed offline (onnxruntime)
    for key in ("data_dir", "seed_dir", "ocr_handoff_path", "vendor_path"):
        p = Path(cfg[key])
        cfg[key] = str(p if p.is_absolute() else ROOT / p)
    if Path(cfg["vendor_path"]).is_dir() and cfg["vendor_path"] not in sys.path:
        sys.path.append(cfg["vendor_path"])
    return cfg
