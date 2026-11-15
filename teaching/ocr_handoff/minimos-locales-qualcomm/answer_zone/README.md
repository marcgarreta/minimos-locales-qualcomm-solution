# answer_zone: read the options A) to E) from an M3Kang image

M3Kang keeps the five options only in the image. The challenge repository's
[`laptop/prepare_m3kang.py`](https://github.com/mpous/datathon-UPC-maths-qualcomm-arduino-unoq) runs
a full-page OCR (text detection + recognition) on the laptop and then guesses which
boxes are the options. This module does it the other way round, and is light
enough to run on the Arduino UNO Q:

1. **Segment.** Find the markers `A)` `B)` `C)` `D)` `E)` by template matching
   (M3Kang draws them with the same LaTeX font), pick the five that read in order,
   and crop the **answer zone**: from `A)` to the end of the `E)` value, plus a margin.
2. **Cut one cell per option**: the ink to the right of each marker, up to the
   next one. A cell is `text` (one line), `fraction` (stacked numerator and
   denominator), `figure` (a drawing, taller than a line) or `empty`.
3. **OCR one line per cell.** Text options are always on one line, so there is no
   detection step: one small recognition pass (PP-OCRv4, ONNX) per cell, all five in
   one batch. A fraction is read as two lines and returned as `num/den`.
4. **Fail loudly.** If any letter has no text value (no marker, a figure, an empty
   cell, OCR read nothing or with low confidence), `extract_options` raises
   `OptionsUnavailable`, naming each letter and the reason.

```
answer_zone/
  segment.py      markers, layout, answer zone, cells (numpy + Pillow only)
  ocr.py          single-line recognizers: onnxruntime (default) or tesseract --psm 7
  extract.py      extract() / extract_options() / zone_image(), the errors
  visualize.py    debug picture: markers, cells, zone, values
  __main__.py     command line: python3 -m answer_zone image.png
  templates/      A.png .. E.png, the marker glyphs (built by tools/build_templates.py)
  models/         ch_PP-OCRv4_rec_infer.onnx (10.9 MB, Apache 2.0; tools/fetch_model.py)
  tests/          unittest, runs on the board too
  tools/          laptop helpers: download images, reference OCR, templates, evaluation, examples
```

## Use it

```python
from answer_zone import extract_options, extract, OptionsUnavailable

try:
    options = extract_options("data/images/lvl-0_2015_13_eng.png")
    # {"A": "12", "B": "15", "C": "18", "D": "20", "E": "24"}
except OptionsUnavailable as e:
    print(e)              # options not available for 5 of 5 letters (A: figure, not text, ...)
    print(e.problems)     # {"A": "figure, not text", ...}
    print(e.result.values())   # the letters that *were* read

r = extract(path)          # never raises: r.ok, r.values(), r.problems, r.zone, r.seconds
```

The input can be a path, PNG bytes (the `image` column of the parquet), a PIL image
or a numpy array.

```bash
python3 -m answer_zone data/images/lvl-0_2015_13_eng.png
python3 -m answer_zone data/images/*.png --json > options.jsonl
python3 -m answer_zone img.png --zone-out zone.png --debug-out debug.png --strict
```

`--strict` exits with code 2 if any image is missing an option.

## Install on the UNO Q

The segmentation needs only numpy and Pillow, both from apt. The OCR needs one of:

**Option 1, onnxruntime (default, more accurate).** One wheel in a venv that also
sees the apt packages:

```bash
sudo apt-get install -y python3-numpy python3-pil python3-venv
python3 -m venv --system-site-packages ~/venvs/answer-zone
~/venvs/answer-zone/bin/pip install onnxruntime
```

Copy the model from the laptop (it's in `answer_zone/models/` after
`python answer_zone/tools/fetch_model.py`):

```bash
scp -r answer_zone/models arduino@<board-ip>:~/minimos-locales-qualcomm/answer_zone/
```

**Option 2, tesseract (apt only, no pip).**

```bash
sudo apt-get install -y python3-numpy python3-pil tesseract-ocr
python3 -m answer_zone img.png --backend tesseract
```

`--backend auto` (the default) uses onnxruntime when it is installed, and falls
back to tesseract.

Check:

```bash
~/venvs/answer-zone/bin/python -m unittest discover -s answer_zone/tests -v
```

The synthetic tests need no M3Kang data. The real-image tests run only where
`data/images_eng/` exists, or where `ANSWER_ZONE_IMAGES` points to the images.

## Measure it on your laptop

```bash
pip install huggingface_hub pyarrow pillow numpy onnxruntime rapidocr_onnxruntime
python answer_zone/tools/fetch_images.py --out data/images_eng      # 393 MB shard, 1,747 English PNGs
python answer_zone/tools/fetch_model.py
python answer_zone/tools/evaluate.py --images data/images_eng        # coverage, reasons, time
python answer_zone/tools/make_examples.py                            # annotated pictures
```

`tools/reference_ocr.py` runs the challenge repository's original full-page OCR on
the same images (`--challenge-repo` points at your clone of it), so `evaluate.py`
can compare the two. `tools/build_templates.py` rebuilds
the marker templates from it.

**Don't commit `data/`**: the images and the evaluation files contain M3Kang
problems, which are for research use only. `.gitignore` already excludes them.
The templates are five glyphs of the letters A to E, and the model is PaddleOCR's.

## Results (English, high_quality shard 0, 1,747 images, laptop)

| | Original `prepare_m3kang.py` (README step 9) | answer_zone |
| --- | --- | --- |
| Five options read, all problems | 1,078 / 1,747 (62%) | **1,490 / 1,747 (85.3%)** |
| Five options read, text-only problems | 601 / 811 (74%) | **804 / 811 (99.1%)** |
| Time per image (laptop CPU) | about 0.5 s (detection + recognition) | 0.19 s median (segmentation 0.11 s) |

- "Read" means five non-empty values with OCR confidence of at least 0.5. There is
  no ground truth for the values. On 209 images where both methods read all five,
  they agree on 93.6% of the values, and the differences we looked at are mostly
  the original parser gluing neighbouring text to a value (`1 15/6/2055` for
  `15/6/2055`, `2 20` for `20`).
- Every failing image says why: 242 have at least one option that is a drawing,
  17 low OCR confidence, 16 an empty cell, 8 OCR read nothing.
- The 7 text-only problems still failing: options wrapped on two lines,
  fractions with a root or π inside, `p·q`-style formulas.
- Not measured on the board yet. Expect several times the laptop time on the
  QRB2210's Cortex-A53 cores: measure with `python3 -m answer_zone img.png --json`
  (`seconds`).

## Limits

- Tuned on the English images (about 1,650 px wide, markers about 30 to 40 px
  tall). The template search covers 0.8x to 1.25x that size.
- Options that are formulas OCR can't spell (roots in exponents, matrices,
  mixed numbers) come out approximate. `√` is recovered from `V`, `cm2` becomes `cm²`.
- A value that is a picture is reported as `figure, not text`, by design: the
  copilot only wants text options.
