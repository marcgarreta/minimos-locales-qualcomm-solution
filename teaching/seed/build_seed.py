"""Build the problem bank that the portal imports on first start (runs on the laptop).

    .venv/Scripts/python arduino/seed/build_seed.py            # text + labels + images + options
    .venv/Scripts/python arduino/seed/build_seed.py --no-options

Inputs (searched in the repo root and in its parent folder; override with the flags):
  seed/categories_eng.json                    topic / subtopic / level of each M3Kang problem
  data/texts.parquet                          English text ('clean', number removed) and answer label
  data/images_eng/<id>_eng.png                problem image (answer_zone/tools/fetch_images.py)
  answer_zone/                                reads options A) .. E) from each image

Outputs (arduino/seed/):
  problems.jsonl     one problem per line
  categories_eng.json  copy, the portal reads the topic taxonomy from it
  images/<id>.png    copies of the images

M3Kang is research-only: don't publish this folder.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BASES = [REPO, REPO.parent, REPO.parent / "datathon-UPC-maths-qualcomm-arduino-unoq",
         REPO / "datathon-UPC-maths-qualcomm-arduino-unoq", REPO / "minimos-locales-qualcomm"]


def find(rel):
    for base in [HERE.parent] + BASES:
        if (base / rel).exists():
            return base / rel
    return REPO / rel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-options", action="store_true", help="skip answer_zone OCR")
    ap.add_argument("--categories", default=str(find("seed/categories_eng.json")
                                                if find("seed/categories_eng.json").exists() else find("categories_eng.json")))
    ap.add_argument("--texts", default=str(find("data/texts.parquet")))
    ap.add_argument("--images", default=str(find("data/images_eng")))
    ap.add_argument("--answer-zone", default=str(find("answer_zone").parent))
    a = ap.parse_args()

    import pandas as pd

    cats = json.loads(Path(a.categories).read_text(encoding="utf-8"))
    if Path(a.categories).resolve() != (HERE / "categories_eng.json").resolve():
        shutil.copy(a.categories, HERE / "categories_eng.json")
    texts = pd.read_parquet(a.texts)
    texts = texts[texts.language == "eng"].set_index("id")

    extract = None
    if not a.no_options:
        sys.path.insert(0, a.answer_zone)
        from answer_zone import extract as _extract, load_recognizer
        rec = load_recognizer("auto")
        extract = lambda p: _extract(str(p), recognizer=rec)  # noqa: E731

    img_dir = Path(a.images)
    out_img = HERE / "images"
    out_img.mkdir(exist_ok=True)
    n_opts = 0
    with open(HERE / "problems.jsonl", "w", encoding="utf-8") as f:
        for i, c in enumerate(cats):
            pid = c["id"]
            if pid not in texts.index:
                continue
            t = texts.loc[pid]
            src = img_dir / f"{pid}_eng.png"
            image = None
            options = {}
            if src.exists():
                image = f"{pid}.png"
                if not (out_img / image).exists():
                    shutil.copy(src, out_img / image)
                if extract:
                    try:
                        options = extract(src).values()
                    except Exception as e:  # keep going, options are optional
                        print(pid, "answer_zone error:", e, file=sys.stderr)
            n_opts += len(options) == 5
            f.write(json.dumps({
                "id": pid, "topic": c["topic"], "subtopic": c["subtopic"], "level": int(c["level"]),
                "text": str(t["clean"]).strip(), "answer": str(t["label"]).strip(),
                "options": options, "image": image, "year": int(t["year"]),
            }, ensure_ascii=False) + "\n")
            if i % 100 == 0:
                print(f"{i}/{len(cats)}", flush=True)
    print(f"done, {len(cats)} problems, {n_opts} with five options read")


if __name__ == "__main__":
    main()
