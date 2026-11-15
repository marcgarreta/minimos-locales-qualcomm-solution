"""Extract English A-E options and export inputs for reason.py / solve2.py.

Run from the project root: .venv/bin/python src/extract_answer_zone.py
Uses existing data/images, never generates image descriptions or correct answers.
The source dataset supplies labels; OCR supplies only candidate option text.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
import hashlib
import json
import multiprocessing
from pathlib import Path
import re
import statistics
import shutil
import subprocess
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "minimos-locales-qualcomm"
sys.path.insert(0, str(PACKAGE))
LETTERS = "ABCDE"
RECOGNIZER = None


@lru_cache(maxsize=1)
def extractor_fingerprint():
    paths = [Path(__file__)] + sorted((PACKAGE / "answer_zone").glob("*.py"))
    paths += sorted((PACKAGE / "answer_zone/templates").glob("*.png"))
    paths += [PACKAGE / "answer_zone/models/ch_PP-OCRv4_rec_infer.onnx"]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def initialize():
    global RECOGNIZER
    from answer_zone import load_recognizer
    RECOGNIZER = load_recognizer("onnx", threads=1)


def extract_one(problem):
    from answer_zone import extract
    image_path = ROOT / "data/images" / (problem["id"] + ".png")
    try:
        result = extract(str(image_path), recognizer=RECOGNIZER).to_dict()
    except Exception as error:
        result = {"ok": False, "options": {}, "problems": {"image": str(error)},
                  "warnings": [], "details": {}, "seconds": {},
                  "error_type": type(error).__name__}
    result.update(id=problem["id"], level=problem["level"],
                  text_only=problem["text_only"], image=str(image_path.relative_to(ROOT)),
                  extractor_fingerprint=extractor_fingerprint(),
                  image_sha256=hashlib.sha256(image_path.read_bytes()).hexdigest())
    return result


def write_jsonl(path, rows):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def is_validation(problem_id):
    # Match the official prepare_m3kang.py default 15% split by problem ID.
    return int(hashlib.sha256(problem_id.encode()).hexdigest(), 16) % 1000 < 150


def prepare_options(problem, extraction):
    """Apply context-based repairs without changing the original OCR cache."""
    options = dict(extraction["options"])
    warnings = list(extraction["warnings"])
    corrections = []
    question = unicodedata.normalize("NFKC", problem["text_eng"])
    variables = set(re.findall(r"\bV\d+\b", question))
    symbols = set(re.findall(r"(?<![A-Za-z])[A-Za-z](?![A-Za-z])", question))
    has_roots = any("√" in value for value in options.values())
    money = bool(re.search(r"\b(?:cents?|euros?|pay|cost|price)\b|€", question, re.I))
    currency = money and any("∈" in value or "€" in value for value in options.values())
    for letter, value in options.items():
        detail = extraction["details"][letter]
        raw = unicodedata.normalize("NFKC", detail["raw"]).strip()
        variable = re.match(r"(V\d+)\b", raw)
        # Upstream assumes an initial V followed by digits means a radical.
        # Preserve a variable explicitly named in the question instead.
        if (detail["kind"] == "text" and variable
                and variable.group(1) in variables and value.startswith("√")):
            options[letter] = "V" + value[1:]
            corrections.append({"letter": letter, "before": value,
                                "after": options[letter],
                                "reason": "preserve variable named in question"})
        before = options[letter]
        value = before
        # Repair only symbol confusions supported by the question's vocabulary.
        if "x" in symbols and not ({"c", "C"} & symbols):
            value = re.sub(r"(?<![A-Za-z])[cC](?![A-Za-z])", "x", value)
        for symbol in symbols:
            other = symbol.swapcase()
            if other not in symbols:
                value = re.sub(r"(?<![A-Za-z])" + other + r"(?![A-Za-z])", symbol, value)
        if has_roots and not variables and not ({"v", "V"} & symbols):
            value = re.sub(r"(?<![A-Za-z])[vV](?=\d)", "√", value)
        value = re.sub(r"∞0\b", "∞", value)
        if re.search(r"\bsets?\b", question, re.I):
            match = re.fullmatch(r"[\[{]+\s*(-?\d+(?:\s*,\s*-?\d+){2,})\s*[\]}]+", value)
            if match:
                value = "{" + match[1] + "}"
        alternate = re.fullmatch(r"([a-z])o([a-z])", value)
        if alternate and {alternate[1], alternate[2]} <= symbols and "o" not in symbols:
            value = alternate[1] + " o " + alternate[2]
        if currency:
            value = value.replace("∈", "€")
            if re.fullmatch(r"\d+(?:[.,]\d+)?", value):
                value += " €"
        if value != before:
            corrections.append({"letter": letter, "before": before, "after": value,
                                "reason": "context-supported symbol normalization"})
        options[letter] = value
    ambiguous = [letter for letter, value in options.items()
                 if "√" in value and "." in value]
    if ambiguous:
        warnings.append("radical expression needs review: period may be a multiplication dot "
                        "(" + ", ".join(ambiguous) + ")")
    for letter, value in options.items():
        stack = []
        malformed = False
        for char in value:
            if char in "([{":
                stack.append(char)
            elif char in ")]}":
                if not stack or {")": "(", "]": "[", "}": "{"}[char] != stack.pop():
                    malformed = True
                    break
        if stack or malformed:
            warnings.append(f"{letter}: unbalanced mathematical brackets")
        if re.search(r"[=+*/-]\s*(?:$|\^)|\?", value):
            warnings.append(f"{letter}: incomplete mathematical expression")
        if re.search(r"[\u3400-\u9fff]", value):
            warnings.append(f"{letter}: unexpected OCR character")
        if "π" in question and re.search(r"/[Tn]\b", value):
            warnings.append(f"{letter}: ambiguous pi glyph in fraction")
        if any("∞" in v for v in options.values()) and re.search(r"[<>≤≥]\s*\+8\b|=\s*-?\d+0[a-z]=", value):
            warnings.append(f"{letter}: ambiguous infinity or alternative separator")
    return options, warnings, corrections


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    data = ROOT / "data"
    problems = [json.loads(line) for line in (data / "problems.jsonl").open() if line.strip()]
    assert len({p["id"] for p in problems}) == len(problems), "Duplicate problem IDs"
    raw_path = data / "answer_zone_extractions.jsonl"
    raw = {}
    if raw_path.exists():
        raw = {r["id"]: r for r in map(json.loads, raw_path.open())}
    fingerprint = extractor_fingerprint()
    pending = [p for p in problems if p["id"] not in raw
               or raw[p["id"]].get("extractor_fingerprint") != fingerprint
               or raw[p["id"]].get("image_sha256") != hashlib.sha256(
                   (data / "images" / (p["id"] + ".png")).read_bytes()).hexdigest()]
    if pending and raw_path.exists():
        old_fingerprint = next(iter(raw.values())).get("extractor_fingerprint", "legacy")[:12]
        backup = raw_path.with_name(raw_path.stem + "." + old_fingerprint + ".jsonl")
        if not backup.exists():
            shutil.copy2(raw_path, backup)
    started = time.monotonic()
    print(f"Extracting {len(pending)} images ({len(raw)} cached), {args.workers} workers", flush=True)
    if pending:
        with raw_path.open("a", encoding="utf-8") as stream, ProcessPoolExecutor(
            max_workers=args.workers, initializer=initialize,
            mp_context=multiprocessing.get_context("spawn"),
        ) as pool:
            for count, row in enumerate(pool.map(extract_one, pending, chunksize=4), 1):
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                raw[row["id"]] = row
                if count % 100 == 0 or count == len(pending):
                    print(f"{count}/{len(pending)} processed in {time.monotonic()-started:.1f}s", flush=True)

    complete, failures = [], []
    for problem in problems:
        extraction = raw[problem["id"]]
        options = extraction["options"]
        if not extraction["ok"] or set(options) != set(LETTERS) or not all(options.values()):
            failures.append(extraction)
            continue
        options, warnings, corrections = prepare_options(problem, extraction)
        row = {k: v for k, v in problem.items() if k not in ("text_eng", "text_cat")}
        row.update(language="eng", text=problem["text_eng"], options=options,
                   options_source="answer_zone", options_verified=False,
                   ocr_warnings=warnings, ocr_corrections=corrections,
                   ocr_min_confidence=min(d["confidence"] for d in extraction["details"].values()))
        complete.append(row)
    text_only = [r for r in complete if r["text_only"]]
    # Preserve suspicious options in the full exports, but exclude them from
    # the recommended train/validation inputs until reviewed.
    clean_text = [r for r in text_only if not r["ocr_warnings"]]
    exports = {
        "answer_zone_all": complete,
        "answer_zone_text": text_only,
        "answer_zone_train": [r for r in clean_text if not is_validation(r["id"])],
        "answer_zone_val": [r for r in clean_text if is_validation(r["id"])],
        "answer_zone_failures": failures,
    }
    for name, rows in exports.items():
        write_jsonl(data / (name + ".jsonl"), rows)
    # Put the cache in source order as well, including when resuming.
    write_jsonl(raw_path, [raw[p["id"]] for p in problems])
    reasons = Counter(reason for r in failures
                      for reason in {message.split(" (")[0] for message in r["problems"].values()})
    timings = [raw[p["id"]]["seconds"]["total"] for p in problems
               if "total" in raw[p["id"]]["seconds"]]
    per_level = {}
    for level in sorted({p["level"] for p in problems}):
        per_level[level] = {
            "total": sum(p["level"] == level for p in problems),
            "complete": sum(p["level"] == level for p in complete),
            "text_only_complete": sum(p["level"] == level for p in text_only),
        }
    summary = {
        "source_repository": "https://github.com/marcgarreta/minimos-locales-qualcomm",
        "source_commit": (PACKAGE / "SOURCE_COMMIT.txt").read_text().strip(),
        "extractor_fingerprint": fingerprint,
        "model_sha256": hashlib.sha256((PACKAGE / "answer_zone/models/ch_PP-OCRv4_rec_infer.onnx").read_bytes()).hexdigest(),
        "problems": len(problems), "complete_options": len(complete),
        "text_only_total": sum(p["text_only"] for p in problems),
        "text_only_complete": len(text_only),
        "complete_with_duplicate_warning": sum(any(w.startswith("two options read the same") for w in r["ocr_warnings"]) for r in complete),
        "text_only_with_duplicate_warning": sum(any(w.startswith("two options read the same") for w in r["ocr_warnings"]) for r in text_only),
        "text_only_with_review_warning": len(text_only) - len(clean_text),
        "records_with_context_corrections": sum(bool(r["ocr_corrections"]) for r in complete),
        "failure_reasons": dict(reasons), "by_level": per_level,
        "files": {str((data / (name + ".jsonl")).relative_to(ROOT)): len(rows)
                  for name, rows in exports.items()},
        "split": "Official sha256(id) modulo 1000 < 150; text-only without OCR review warnings",
        "timing": {"machine": "laptop CPU, concurrent workers", "workers": args.workers,
                   "images_extracted_this_run": len(pending),
                   "median_seconds_per_image": statistics.median(timings) if timings else None,
                   "extraction_wall_seconds_this_run": round(time.monotonic()-started, 2)},
        "caveat": "Coverage is not transcription accuracy. Options are unverified OCR. Figure content is not extracted.",
    }
    report = ROOT / "results/answer_zone_summary.json"
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
