"""Figures and answer pictures of the bank, from the team's OCR handoff (runs on the laptop).

    .venv/Scripts/python arduino/seed/build_figures.py --handoff ocr_handoff_zip/ocr_handoff/data

The handoff (wetransfer "ocr_handoff") already ran its pipeline on the 1,747 English problems:
answer_zone_multimodal_all.jsonl + multimodal/<id>/{question,A..E}.png. This copies the crops the
app uses into seed/multimodal/ (16 grey levels: ~3x smaller, same look) and writes seed/figures.json:

    {id: {"figure": "multimodal/<id>/question.png" | "images/<id>.png" (fallback page) | null,
          "fallback": bool, "options": {A..E: path} | {}, "texts": {A..E: OCR text}, "mode": ...}}

The same layout is produced on the board for photos added by the teacher (app/figures.py).
Both outputs are git-ignored (M3Kang is research-only).
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from app.figures import describe  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--handoff", default=str(HERE.parent.parent.parent / "ocr_handoff_zip/ocr_handoff/data"),
                    help="the handoff's data/ folder")
    a = ap.parse_args()
    from PIL import Image

    src = Path(a.handoff)
    rows = [json.loads(line) for line in open(src / "answer_zone_multimodal_all.jsonl", encoding="utf-8")]
    out_dir = HERE / "multimodal"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    figures, modes = {}, {}
    for row in rows:
        d = describe(row, "")
        fixed = {}
        for key in ("figure",):
            if d[key]:
                fixed[key] = d[key].lstrip("/")
        for L, p in d["options"].items():
            fixed.setdefault("options", {})[L] = p.lstrip("/")
        for p in [fixed.get("figure")] + list(fixed.get("options", {}).values()):
            if p and p.startswith("multimodal/"):
                dest = HERE / p
                dest.parent.mkdir(parents=True, exist_ok=True)
                Image.open(src / p).convert("L").quantize(16).save(dest, optimize=True)
        figures[row["id"]] = {"figure": fixed.get("figure"), "fallback": d["fallback"],
                              "options": fixed.get("options", {}), "texts": d["texts"], "mode": d["mode"]}
        modes[d["mode"]] = modes.get(d["mode"], 0) + 1
    (HERE / "figures.json").write_text(json.dumps(figures, ensure_ascii=False), encoding="utf-8")
    print(f"{len(figures)} problems: " + ", ".join(f"{k} {v}" for k, v in sorted(modes.items())))


if __name__ == "__main__":
    main()
