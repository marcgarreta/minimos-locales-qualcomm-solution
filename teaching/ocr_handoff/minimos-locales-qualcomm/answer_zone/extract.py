"""Read the options A) .. E) of an M3Kang image.

    from answer_zone import extract_options, OptionsUnavailable
    try:
        options = extract_options("lvl-0_2015_13_eng.png")   # {"A": "12", ..., "E": "24"}
    except OptionsUnavailable as e:
        print(e.problems)                                      # {"C": "figure, not text", ...}

``extract()`` returns the full result (zone, boxes, scores, problems) without raising.
"""
import re
import time
import unicodedata
from dataclasses import dataclass, field

import numpy as np

from .ocr import load_recognizer
from .segment import LETTERS, load_gray, segment
from .math_layout import fraction_value, power_parts

MIN_CONFIDENCE = 0.5


class AnswerZoneError(Exception):
    """Base class for every error of this module."""


class OptionsUnavailable(AnswerZoneError):
    """At least one option A..E has no text value.

    ``problems`` maps each failing letter to the reason, for example
    ``{"B": "figure, not text", "E": "marker not found"}``. ``result`` holds
    everything that was read, so a caller can still use the good options.
    """

    def __init__(self, problems, result=None):
        self.problems = dict(problems)
        self.result = result
        detail = ", ".join(f"{k}: {v}" for k, v in sorted(self.problems.items()))
        super().__init__(f"options not available for {len(self.problems)} of 5 letters ({detail})")


@dataclass
class Option:
    letter: str
    value: str = ""
    kind: str = "missing"      # text | fraction | figure | empty | missing
    confidence: float = 0.0
    box: tuple = None          # value ink box in the image, (x0, y0, x1, y1)
    marker_box: tuple = None
    raw: str = ""              # OCR output before normalization
    layout: list = field(default_factory=list)


@dataclass
class Extraction:
    options: dict              # letter -> Option, always the five letters
    zone: tuple = None         # answer zone (x0, y0, x1, y1), or None
    problems: dict = field(default_factory=dict)   # letter -> reason
    warnings: list = field(default_factory=list)
    seconds: dict = field(default_factory=dict)    # segment, ocr, total

    @property
    def ok(self):
        return not self.problems

    def values(self):
        """{"A": "12", ...} for the letters that were read."""
        return {k: o.value for k, o in self.options.items() if k not in self.problems}

    def to_dict(self):
        return {
            "ok": self.ok,
            "options": self.values(),
            "zone": list(self.zone) if self.zone else None,
            "problems": self.problems,
            "warnings": self.warnings,
            "details": {k: {"value": o.value, "kind": o.kind, "confidence": round(o.confidence, 3),
                            "box": list(o.box) if o.box else None, "raw": o.raw,
                            "layout": o.layout}
                        for k, o in self.options.items()},
            "seconds": {k: round(v, 3) for k, v in self.seconds.items()},
        }


def normalize(text):
    """OCR text -> clean option value (NFKC, one space, ASCII minus...)."""
    # NFKC flattens Unicode superscripts. Save their mathematical role first.
    superscripts = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
    text = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", lambda m: "^(" + m[0].translate(superscripts) + ")", text)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^V(?=\d)", "√", text)                       # √2 is often read as V2
    text = re.sub(r"(?<![A-Za-z])(mm|cm|dm|km|m)(?:\^\(([23])\)|([23]))(?![A-Za-z0-9])",
                  lambda m: m.group(1) + "²³"[int(m.group(2) or m.group(3)) - 2], text)
    return text.strip(" .,;:")


_RECOGNIZER = None


def _default_recognizer():
    global _RECOGNIZER
    if _RECOGNIZER is None:
        _RECOGNIZER = load_recognizer("auto")
    return _RECOGNIZER


def extract(src, recognizer=None, min_confidence=MIN_CONFIDENCE):
    """Segment + OCR one image. Never raises for a bad image: see ``problems``."""
    t0 = time.perf_counter()
    gray = load_gray(src)
    seg = segment(gray)
    t1 = time.perf_counter()
    options = {L: Option(L) for L in LETTERS}
    problems = {}
    for L in seg.missing:
        problems[L] = "marker not found"
    # Everything that has to be read goes to the recognizer in one batch.
    jobs = []
    layouts = {}
    for L, cell in seg.cells.items():
        opt = options[L]
        opt.kind, opt.box = cell.kind, cell.box
        m = seg.markers[L]
        opt.marker_box = (m.x0, m.y0, m.x1, m.y1)
        if cell.kind == "figure":
            problems[L] = "figure, not text"
        elif cell.kind == "empty":
            problems[L] = "no value next to the marker"
        else:
            plan = ([("text", part) for part in cell.parts] if cell.kind == "fraction"
                    else power_parts(gray, cell.box, m))
            layouts[L] = [kind for kind, _ in plan]
            opt.layout = [{"kind": kind, "box": list(part)} for kind, part in plan]
            for kind, part in plan:
                x0, y0, x1, y1 = part
                jobs.append((L, gray[y0:y1, x0:x1]))
    if jobs:
        recognizer = recognizer or _default_recognizer()
        reads = recognizer.read_lines([crop for _, crop in jobs])
    else:
        reads = []
    per_letter = {}
    for (L, _), (text, score) in zip(jobs, reads):
        per_letter.setdefault(L, []).append((text, score))
    for L, parts in per_letter.items():
        opt = options[L]
        texts = [normalize(t) for t, _ in parts]
        opt.raw = " | ".join(t for t, _ in parts)
        opt.confidence = float(min(s for _, s in parts))
        if opt.kind == "fraction":
            opt.value = fraction_value(*texts)
        else:
            opt.value = "".join("^(" + value + ")" if kind == "power" else value
                                for kind, value in zip(layouts[L], texts))
            opt.value = normalize(opt.value)
        if not all(texts):
            problems[L] = "OCR read nothing"
        elif opt.confidence < min_confidence:
            problems[L] = f"low OCR confidence ({opt.confidence:.2f})"
    t2 = time.perf_counter()
    read = [o.value for L, o in options.items() if L not in problems]
    if len(set(read)) < len(read):
        dupes = sorted({v for v in read if read.count(v) > 1})
        warnings = [f"two options read the same: {', '.join(dupes)}"]
    else:
        warnings = []
    return Extraction(options=options, zone=seg.zone, problems=problems, warnings=warnings,
                      seconds={"segment": t1 - t0, "ocr": t2 - t1, "total": t2 - t0})


def extract_options(src, recognizer=None, min_confidence=MIN_CONFIDENCE):
    """{"A": ..., "E": ...}, or raise OptionsUnavailable naming the letters that failed."""
    result = extract(src, recognizer, min_confidence)
    if result.problems:
        raise OptionsUnavailable(result.problems, result)
    return result.values()


def zone_image(src, result=None, pad=0):
    """The answer zone as a grey array (the crop between A) and the end of E))."""
    gray = load_gray(src)
    zone = (result.zone if result else segment(gray).zone)
    if zone is None:
        raise OptionsUnavailable({L: "marker not found" for L in LETTERS})
    x0, y0, x1, y1 = zone
    H, W = gray.shape
    return gray[max(0, y0 - pad):min(H, y1 + pad), max(0, x0 - pad):min(W, x1 + pad)]
