"""Export text plus original-pixel visual inputs, without generated descriptions.

Run from the project root: .venv/bin/python src/export_multimodal.py
Paths in the JSONL are relative to its parent (data/). The existing text-only
benchmarks are untouched. Image crops are candidates, not audited ground truth.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

from extract_answer_zone import (ROOT, extractor_fingerprint, is_validation,
                                prepare_options, write_jsonl)
from answer_zone.segment import segment

LETTERS = "ABCDE"
cv2.setNumThreads(1)


def rectangle_gap(a, b):
    return (max(0, a[0] - b[2], b[0] - a[2]) ** 2 +
            max(0, a[1] - b[3], b[1] - a[3]) ** 2) ** 0.5


def union_box(boxes, size, pad=8):
    return [max(0, min(b[0] for b in boxes) - pad), max(0, min(b[1] for b in boxes) - pad),
            min(size[0], max(b[2] for b in boxes) + pad),
            min(size[1], max(b[3] for b in boxes) + pad)]


def intersects(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def paragraph_regions(components, h, size, markers):
    """Find long, left-aligned prose lines, without recognizing their content.

    Short labels, dimension strings and stacked calculations are deliberately
    ineligible. These regions guide cropping; their pixels are never erased.
    """
    bottom = min((m.y0 for m in markers.values()), default=size[1])
    glyphs = [b for b in components if 0.3 * h <= b[3] - b[1] <= 1.3 * h
              and b[2] - b[0] <= 1.5 * h and b[3] < bottom]
    lines = []
    for b in sorted(glyphs, key=lambda b: (b[3], b[0])):
        line = next((line for line in reversed(lines)
                     if abs(np.median([g[3] for g in line]) - b[3]) <= 0.25 * h), None)
        if line is None:
            lines.append([b])
        else:
            line.append(b)
    paragraphs = []
    for line in lines:
        groups = []
        for b in sorted(line, key=lambda b: b[0]):
            # Keep this gap conservative: a nearby diagram label can share
            # the prose baseline. Retaining a prose fragment is preferable
            # to swallowing a separate point label into the paragraph.
            if not groups or b[0] - max(g[2] for g in groups[-1]) > 0.75 * h:
                groups.append([])
            groups[-1].append(b)
        for group in groups:
            box = union_box(group, size, 0)
            if len(group) >= 18 and box[0] < 0.2 * size[0] and box[2] - box[0] > 0.28 * size[0]:
                # Include dots/accents belonging to this prose line.
                paragraphs.append([max(0, box[0] - 3), max(0, box[1] - int(0.3 * h)),
                                   min(size[0], box[2] + int(0.4 * h)), min(size[1], box[3] + 3)])
    return paragraphs


def connected_labels(seeds, components, distance):
    """Grow through entire nearby labels, ellipses and multiline expressions.

    Testing only distance to the large graphic loses the far end of a label.
    Connectivity propagates until stable, not just one fixed padding step.
    """
    selected = list(seeds)
    pending = [b for b in components if b not in seeds]
    frontier = list(seeds)
    while frontier:
        added = [b for b in pending if any(rectangle_gap(b, g) <= distance for g in frontier)]
        if not added:
            break
        selected.extend(added)
        pending = [b for b in pending if b not in added]
        frontier = added
    return selected


def visual_regions(image, markers, extraction, image_options, needs_context):
    """Locate graphic components, associate choices, and retain diagram labels.

    This is a layout heuristic, not a semantic diagram detector. Do not erase
    text: the final crop comes from the original pixels, including annotations.
    """
    h = float(np.median([m.h for m in markers.values()])) if markers else 36.0
    ink = (np.asarray(image.convert("L")) < 235).astype(np.uint8)
    _, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    components = [[int(x), int(y), int(x + w), int(y + height)]
                  for x, y, w, height, area in stats[1:] if area >= 3]
    prose = paragraph_regions(components, h, image.size, markers)
    graphics = [b for b in components if max(b[2] - b[0], b[3] - b[1]) >= max(45, 1.5 * h)]
    boxes, warnings = option_regions(image, markers) if image_options else ({}, [])
    # When page text/side diagrams cross a row's gutters, find each answer's
    # drawing by proximity to its marker instead of cropping entire columns.
    if image_options and warnings and set(markers) == set(LETTERS):
        pairs = []
        for letter, m in markers.items():
            mb = [m.x0, m.y0, m.x1, m.y1]
            for index, box in enumerate(graphics):
                gap = rectangle_gap(mb, box)
                if gap < 2 * h and box[2] > m.x0 and box[0] > m.x0 - h:
                    pairs.append((gap, letter, index))
        assigned, used = {}, set()
        for _, letter, index in sorted(pairs):
            if letter not in assigned and index not in used:
                assigned[letter] = graphics[index]
                used.add(index)
        if set(assigned) == set(LETTERS):
            candidate = {}
            for letter, seed in assigned.items():
                marker_boxes = [[m.x0, m.y0, m.x1, m.y1] for m in markers.values()]
                nearby = [b for b in components if rectangle_gap(b, seed) <= 0.4 * h
                          and (b == seed or max(b[2] - b[0], b[3] - b[1]) < 1.5 * h)
                          and not any(min(b[2], mb[2]) > max(b[0], mb[0]) and
                                      min(b[3], mb[3]) > max(b[1], mb[1]) for mb in marker_boxes)]
                # Captions carry A-E. Including a marker above the drawing can
                # pull a corner of the question diagram into its bounding box.
                candidate[letter] = union_box([seed, *nearby], image.size, 6)
            overlap = any(min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])
                          for i, a in enumerate(candidate.values()) for b in list(candidate.values())[i + 1:])
            if not overlap:
                boxes, warnings = candidate, []

    # Numeric/text choices also need masking for diagram discovery, but these
    # boxes are never erased from a final image.
    excluded = list(boxes.values()) if image_options and not warnings else [
        d["box"] for d in extraction["details"].values() if d.get("box")]
    remaining = []
    for box in graphics:
        overlaps = []
        for ex in excluded:
            area = max(0, min(box[2], ex[2]) - max(box[0], ex[0])) * max(0, min(box[3], ex[3]) - max(box[1], ex[1]))
            overlaps.append(area / max(1, (box[2] - box[0]) * (box[3] - box[1])))
        if overlaps and max(overlaps) > 0.8:
            continue
        if overlaps and max(overlaps) > 0.05:
            warnings.append("a graphic crosses an option crop boundary")
        remaining.append(box)
    context = None
    if needs_context and remaining:
        marker_boxes = [[m.x0 - 2, m.y0 - 2, m.x1 + 2, m.y1 + 2] for m in markers.values()]
        labels = [b for b in components
                  if not any(intersects(b, ex) for ex in excluded + marker_boxes + prose)]
        # Small detached legends can be below the large-graphic threshold.
        # Admit them near an existing diagram, but do not enlarge the linking
        # radius for ordinary text/dots (which would collect unrelated prose).
        satellites = [b for b in labels if max(b[2] - b[0], b[3] - b[1]) >= max(32, 1.2 * h)
                      and any(rectangle_gap(b, g) <= 2 * h for g in remaining)]
        selected = connected_labels(remaining + satellites, labels, 0.8 * h)
        context = union_box(selected, image.size, 10)
        # A single rectangular crop must not mix diagram pixels with choices.
        if any(min(context[2], ex[2]) > max(context[0], ex[0]) and
               min(context[3], ex[3]) > max(context[1], ex[1]) for ex in excluded):
            warnings.append("diagram and choices cannot be cleanly separated in one rectangle")
    elif needs_context and not image_options:
        warnings.append("no confident complementary diagram region")
    return boxes, context, sorted(set(warnings))


def save_panel(assets, data, path):
    """One labeled panel for comparing single-image versus multi-image inference."""
    tiles = []
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 26)
    except OSError:
        font = ImageFont.load_default()
    for asset in assets:
        with Image.open(data / asset["path"]) as source:
            im = source.convert("RGB")
        label = "Question diagram" if asset["role"] == "diagram" else (
            asset["letter"] + ")" if asset["role"] == "option" else "Original problem")
        label_box = font.getbbox(label)
        tile = Image.new("RGB", (max(im.width + 20, label_box[2] - label_box[0] + 20), im.height + 50), "white")
        ImageDraw.Draw(tile).text((10, 5), label, font=font, fill="black")
        tile.paste(im, (10, 40))
        tiles.append((asset["role"], tile))
    contexts = [im for role, im in tiles if role != "option"]
    options = [im for role, im in tiles if role == "option"]
    cell_w = max((im.width for im in options), default=0)
    cell_h = max((im.height for im in options), default=0)
    # Long line drawings become unreadable when three are placed side by side
    # and a vision encoder subsequently scales the whole panel down.
    columns = 1 if cell_w > 600 else (5 if cell_w < 230 else 3)
    gap = 12
    width = max([im.width for im in contexts] + [columns * (cell_w + gap) - gap, 180])
    top_h = sum(im.height + gap for im in contexts)
    height = top_h + ((len(options) + columns - 1) // columns) * (cell_h + gap)
    panel = Image.new("RGB", (width, height), "white")
    y = 0
    for im in contexts:
        panel.paste(im, ((width - im.width) // 2, y))
        y += im.height + gap
    for i, im in enumerate(options):
        panel.paste(im, ((i % columns) * (cell_w + gap), y + (i // columns) * (cell_h + gap)))
    panel.save(path)


def option_regions(image, markers):
    """Partition marker rows at white gutters, retaining letters and whole cells.

    The OCR's tight ink boxes can truncate drawings or select a nearby diagram.
    Use wider cells instead. If a boundary is uncertain, keep candidate crops for
    inspection but send the original page instead of those crops.
    """
    if set(markers) != set(LETTERS):
        return {}, ["not all five option markers were located"]
    ink = np.asarray(image.convert("L")) < 235
    height, width = ink.shape
    rows = []
    for marker in sorted(markers.values(), key=lambda m: (m.cy, m.x0)):
        if not rows or abs(marker.cy - np.median([m.cy for m in rows[-1]])) > marker.h:
            rows.append([])
        rows[-1].append(marker)
    rows = [sorted(row, key=lambda m: m.x0) for row in rows]
    if "".join(m.letter for row in rows for m in row) != LETTERS:
        return {}, ["option markers are not in A-E reading order"]

    warnings, bands = [], []
    for index, row in enumerate(rows):
        h = int(np.median([m.h for m in row]))
        spacing = np.median(np.diff([m.x0 for m in row])) if len(row) > 1 else None
        left = max(0, row[0].x0 - h)
        right = min(width, int(row[-1].x0 + spacing - h / 2)) if spacing else width
        marker_top = min(m.y0 for m in row)
        lower = max(m.y1 for m in rows[index - 1]) if index else 0
        blanks = np.flatnonzero(~ink[lower:marker_top, left:right].any(axis=1)) + lower
        if len(blanks):
            top = int(blanks[-1])
        else:
            top = max(lower, marker_top - h // 2)
            warnings.append("no clear upper gutter for option row " + row[0].letter)
        bands.append((top, left, right, h))

    boxes = {}
    for index, row in enumerate(rows):
        top, left, right, h = bands[index]
        bottom = bands[index + 1][0] if index + 1 < len(bands) else height
        if bottom <= max(m.y1 for m in row):
            warnings.append("overlapping option rows")
            continue
        boundaries = [left]
        for marker in row[1:]:
            lo, hi = max(left, marker.x0 - h), min(right, marker.x0)
            blanks = np.flatnonzero(~ink[top:bottom, lo:hi].any(axis=0)) + lo
            if len(blanks):
                boundary = int(min(blanks, key=lambda x: abs(x - (marker.x0 - h / 2))))
            else:
                boundary = max(left, marker.x0 - h // 2)
                warnings.append("no clear left gutter for option " + marker.letter)
            boundaries.append(boundary)
        boundaries.append(right)
        for marker, x0, x1 in zip(row, boundaries, boundaries[1:]):
            if x1 <= x0:
                warnings.append("empty cell for option " + marker.letter)
                continue
            if ink[top:bottom, x0].any() or (x1 < width and ink[top:bottom, x1].any()):
                warnings.append("ink crosses a cell boundary for option " + marker.letter)
            ys, xs = np.nonzero(ink[top:bottom, x0:x1])
            if not len(xs):
                warnings.append("no pixels for option " + marker.letter)
                continue
            boxes[marker.letter] = [max(x0, int(x0 + xs.min()) - 6),
                                    max(top, int(top + ys.min()) - 6),
                                    min(x1, int(x0 + xs.max()) + 7),
                                    min(bottom, int(top + ys.max()) + 7)]
    return boxes, sorted(set(warnings))


def export_record(problem, extraction, data):
    options, warnings, corrections = prepare_options(problem, extraction)
    figure_letters = [k for k, d in extraction["details"].items() if d["kind"] == "figure"]
    image_options = bool(figure_letters or extraction["problems"] or warnings)
    requires_vision = not problem["text_only"] or image_options
    row = {k: v for k, v in problem.items() if k not in ("text_eng", "text_cat")}
    row.update(language="eng", text=problem["text_eng"], options=options,
               options_source="answer_zone", options_verified=False,
               ocr_warnings=warnings, ocr_corrections=corrections,
               requires_vision=requires_vision, vision_reasons=[], images=[],
               option_images={}, context_images=[], image_warnings=[], images_verified=False)
    if not problem["text_only"]:
        row["vision_reasons"].append("dataset marks problem as not text-only")
    if image_options:
        row["vision_reasons"].append("picture choices or incomplete/ambiguous option OCR")
    if not requires_vision:
        return row

    source = data / "images" / (problem["id"] + ".png")
    row["source_image_sha256"] = extraction["image_sha256"]
    row["source_image"] = {"role": "problem", "path": str(source.relative_to(data)),
                           "sha256": extraction["image_sha256"]}
    row["context_image_policy"] = "crop diagram with nearby labels; original page on uncertain separation"
    with Image.open(source) as opened:
        image = opened.convert("RGB")
    markers = segment(image).markers
    boxes, context, crop_warnings = visual_regions(
        image, markers, extraction, image_options, not problem["text_only"])
    row["image_warnings"] = crop_warnings
    directory = data / "multimodal" / problem["id"]
    directory.mkdir(parents=True, exist_ok=True)
    if context:
        path = directory / "question.png"
        image.crop(context).save(path)
        row["context_images"].append({"role": "diagram", "path": str(path.relative_to(data)),
                                      "box": context, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if image_options:
        for letter, box in boxes.items():
            path = directory / (letter + ".png")
            crop = image.crop(box)
            # One canonical A) caption is added by the prompt/panel. Remove the
            # original marker (or its clipped tail), without erasing figure labels.
            marker = markers[letter]
            marker_box = [marker.x0 - 2, marker.y0 - 2, marker.x1 + 2, marker.y1 + 2]
            ImageDraw.Draw(crop).rectangle((marker_box[0] - box[0], marker_box[1] - box[1],
                                           marker_box[2] - box[0], marker_box[3] - box[1]), fill="white")
            crop.save(path)
            asset = {"role": "option", "letter": letter, "path": str(path.relative_to(data)),
                     "box": box, "removed_marker_box": marker_box,
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            row["option_images"][letter] = asset
        # A picture can be mistaken for text (e.g. circles -> OOO). When any
        # option needs images, take all five from pixels rather than mixed OCR.
        row["options"] = {letter: "[see option " + letter + " in the images]" for letter in LETTERS}
    usable = not crop_warnings and (not image_options or set(boxes) == set(LETTERS))
    if usable:
        row["images"] = row["context_images"] + [row["option_images"][letter] for letter in LETTERS if letter in row["option_images"]]
        row["image_mode"] = ("diagram_and_option_crops" if context else "option_crops") if image_options else "diagram_with_text_options"
    else:
        row["images"] = [row["source_image"]]
        row["image_mode"] = "original_page_fallback"
    choices = [asset for asset in row["images"] if asset["role"] == "option"]
    if choices:
        answer_panel = directory / "answers.png"
        save_panel(choices, data, answer_panel)
        row["answer_panel"] = {"role": "answers", "path": str(answer_panel.relative_to(data)),
                               "sha256": hashlib.sha256(answer_panel.read_bytes()).hexdigest()}
    panel = directory / "panel.png"
    save_panel(row["images"], data, panel)
    row["image_panel"] = {"role": "panel", "path": str(panel.relative_to(data)),
                          "sha256": hashlib.sha256(panel.read_bytes()).hexdigest()}
    return row


def export_job(job):
    problem, extraction, data = job
    return export_record(problem, extraction, Path(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="debug subset; writes separate sample files")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.limit < 0 or args.workers < 1:
        parser.error("limit must be nonnegative and workers must be positive")
    data = ROOT / "data"
    problems = [json.loads(s) for s in (data / "problems.jsonl").read_text().splitlines()]
    cache = {r["id"]: r for r in map(json.loads, (data / "answer_zone_extractions.jsonl").read_text().splitlines())}
    if args.limit:
        problems = problems[:args.limit]
    fingerprint = extractor_fingerprint()
    jobs = []
    for problem in problems:
        cached = cache[problem["id"]]
        source = data / "images" / (problem["id"] + ".png")
        if (cached.get("extractor_fingerprint") != fingerprint or
                cached["image_sha256"] != hashlib.sha256(source.read_bytes()).hexdigest()):
            raise ValueError("Stale extraction for " + problem["id"] + "; rerun extract_answer_zone.py")
        jobs.append((problem, cached, str(data)))
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        for number, row in enumerate(pool.map(export_job, jobs, chunksize=4), 1):
            rows.append(row)
            if number % 200 == 0:
                print(f"Exported {number}/{len(problems)}", flush=True)
    prefix = "answer_zone_multimodal" + ("_sample" if args.limit else "")
    splits = {"all": rows,
              "train": [r for r in rows if not is_validation(r["id"])],
              "val": [r for r in rows if is_validation(r["id"])]}
    for name, records in splits.items():
        write_jsonl(data / (prefix + "_" + name + ".jsonl"), records)
    summary = {"extractor_fingerprint": fingerprint,
               "exporter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "files": {prefix + "_" + k + ".jsonl": len(v) for k, v in splits.items()},
               "requires_vision": sum(r["requires_vision"] for r in rows),
               "text_only_inputs": sum(not r["requires_vision"] for r in rows),
               "modes": dict(Counter(r.get("image_mode", "text") for r in rows)),
               "option_crop_files": sum(len(r["option_images"]) for r in rows),
               "question_crop_files": sum(len(r["context_images"]) for r in rows),
               "grouped_answer_files": sum("answer_panel" in r for r in rows),
               "limitations": ["Images and option crops are not exhaustively visually audited.",
                               "text_only is dataset metadata, not proof a diagram is essential.",
                               "Uncertain diagram/choice separation uses an explicit original-page fallback.",
                               "No vision-model accuracy or board latency measured."]}
    (ROOT / "results" / (prefix + "_summary.json")).write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
