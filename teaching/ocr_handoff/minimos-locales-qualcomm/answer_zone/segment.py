"""Find the answer zone of an M3Kang image: the markers A) .. E) and one cell per option.

No OCR here, only numpy and Pillow, so it is cheap on the UNO Q:

1. **Markers.** M3Kang renders the options with LaTeX, so ``A)`` .. ``E)`` always
   have the same glyphs (Computer Modern). Each marker is found by normalized
   cross-correlation with a small template (``templates/A.png`` ..), at a few
   scales, on a half-resolution copy of the image (FFT, a few hundred ms on the board).
2. **Layout.** From the candidates, pick the five that read A, B, C, D, E in
   reading order (one row, two rows, one column...) with the best total score.
3. **Answer zone.** The crop from the A) marker to the end of the E) value, plus
   a margin: this is the "segment" the rest of the pipeline works on.
4. **Cells.** For each marker, the ink to its right, up to the next marker,
   grouped into connected blobs. The value is the chain of blobs that sits on the
   marker's line. Its shape gives its kind:
   ``text`` (one line), ``fraction`` (numerator, bar, denominator), ``figure``
   (taller than a line: a drawing, which we do not read) or ``empty``.
"""
import io
import os
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(HERE, "templates")
LETTERS = "ABCDE"

# Tuned on the English M3Kang images (1653 px wide, markers about 30 px tall).
DOWNSCALE = 2              # marker search runs at half resolution
SCALES = (0.8, 0.9, 1.0, 1.1, 1.25)
MIN_SCORE = 0.55           # NCC needed for a marker candidate
TOP_K = 6                  # candidates kept per letter
INK = 140                  # grey level below which a pixel is ink
FIGURE_HEIGHT = 1.3        # a value taller than this many marker heights is a figure...
FRACTION_HEIGHT = 2.6      # ...unless it is a stacked fraction (up to this tall)


@dataclass
class Marker:
    letter: str
    x0: int
    y0: int
    x1: int
    y1: int
    score: float

    @property
    def h(self):
        return self.y1 - self.y0

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2


@dataclass
class Cell:
    letter: str
    kind: str                  # text | fraction | figure | empty
    box: tuple = None          # (x0, y0, x1, y1) of the value ink, in image pixels
    parts: list = field(default_factory=list)  # boxes to OCR: [line] or [numerator, denominator]


@dataclass
class Segmentation:
    markers: dict              # letter -> Marker (only the letters found)
    zone: tuple = None         # (x0, y0, x1, y1) answer zone crop
    cells: dict = field(default_factory=dict)  # letter -> Cell
    missing: list = field(default_factory=list)  # letters with no marker


# --- image helpers --------------------------------------------------------------

def load_gray(src):
    """Path, bytes, PIL image or array -> uint8 grey array (H, W)."""
    if isinstance(src, np.ndarray):
        arr = src if src.ndim == 2 else np.asarray(Image.fromarray(src).convert("L"))
        return arr.astype(np.uint8)
    if isinstance(src, (bytes, bytearray)):
        src = Image.open(io.BytesIO(src))
    elif isinstance(src, str):
        src = Image.open(src)
    if src.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGBA", src.size, (255, 255, 255, 255))
        src = Image.alpha_composite(bg, src.convert("RGBA"))
    return np.asarray(src.convert("L"), dtype=np.uint8)


def _resize(arr, w, h):
    return np.asarray(Image.fromarray(arr).resize((max(1, w), max(1, h)), Image.BILINEAR))


# --- 1. markers -----------------------------------------------------------------

_TEMPLATES = None


def load_templates(directory=TEMPLATE_DIR):
    global _TEMPLATES
    if _TEMPLATES is None or directory != TEMPLATE_DIR:
        out = {}
        for letter in LETTERS:
            path = os.path.join(directory, f"{letter}.png")
            if not os.path.exists(path):
                raise FileNotFoundError(f"missing marker template {path} (run answer_zone/tools/build_templates.py)")
            out[letter] = np.asarray(Image.open(path).convert("L"), dtype=np.uint8)
        if directory != TEMPLATE_DIR:
            return out
        _TEMPLATES = out
    return _TEMPLATES


def _ncc_maps(image, templates):
    """Normalized cross-correlation of ``image`` (float, ink=1) with each template.

    Returns a list of (map, th, tw): map[y, x] is the score of the template whose
    top-left corner is at (x, y). One FFT of the image, one per template.
    """
    H, W = image.shape
    th_max = max(t.shape[0] for t in templates)
    tw_max = max(t.shape[1] for t in templates)
    fh, fw = _fast_len(H + th_max), _fast_len(W + tw_max)
    F = np.fft.rfft2(image, s=(fh, fw))
    # integral images for the local sums under each template window
    ii = np.pad(image, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    ii2 = np.pad(image * image, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    out = []
    for t in templates:
        th, tw = t.shape
        n = th * tw
        tz = t - t.mean()
        tnorm = np.sqrt((tz * tz).sum())
        if tnorm == 0 or th > H or tw > W:
            out.append((np.zeros((1, 1), np.float32), th, tw))
            continue
        T = np.fft.rfft2(tz[::-1, ::-1], s=(fh, fw))
        corr = np.fft.irfft2(F * T, s=(fh, fw))[th - 1:H, tw - 1:W]
        s1 = ii[th:, tw:] - ii[:-th, tw:] - ii[th:, :-tw] + ii[:-th, :-tw]
        s2 = ii2[th:, tw:] - ii2[:-th, tw:] - ii2[th:, :-tw] + ii2[:-th, :-tw]
        var = np.maximum(s2 - s1 * s1 / n, 0)
        denom = np.sqrt(var) * tnorm
        ncc = np.where(denom > 1e-3 * n, corr / np.maximum(denom, 1e-9), 0)
        out.append((ncc.astype(np.float32), th, tw))
    return out


def _fast_len(n):
    """Next size with only small prime factors, so the FFT is fast."""
    while True:
        m = n
        for p in (2, 3, 5):
            while m % p == 0:
                m //= p
        if m == 1:
            return n
        n += 1


def _peaks(ncc, th, tw, k, min_score):
    """Top-k local maxima with non-maximum suppression over a template-sized area."""
    found = []
    work = ncc.copy()
    for _ in range(k):
        idx = int(np.argmax(work))
        y, x = divmod(idx, work.shape[1])
        score = float(work[y, x])
        if score < min_score:
            break
        found.append((score, x, y))
        work[max(0, y - th):y + th, max(0, x - tw):x + tw] = -1
    return found


def find_candidates(gray, templates=None, scales=SCALES, min_score=MIN_SCORE, top_k=TOP_K):
    """All plausible markers, best first, as a list of Marker (letters may repeat)."""
    templates = templates or load_templates()
    d = DOWNSCALE
    small = _resize(gray, gray.shape[1] // d, gray.shape[0] // d)
    image = (255 - small.astype(np.float32)) / 255.0
    tlist, meta = [], []
    for letter, t in templates.items():
        for s in scales:
            h = max(4, round(t.shape[0] * s / d))
            w = max(3, round(t.shape[1] * s / d))
            tlist.append((255 - _resize(t, w, h).astype(np.float32)) / 255.0)
            meta.append(letter)
    cands = []
    for letter, (ncc, th, tw) in zip(meta, _ncc_maps(image, tlist)):
        for score, x, y in _peaks(ncc, th, tw, top_k, min_score):
            cands.append(Marker(letter, x * d, y * d, (x + tw) * d, (y + th) * d, score))
    # per letter, overlapping hits at different scales are one candidate. Letters are
    # NOT suppressed against each other: "E)" may score well on a "D)", and the
    # layout step (reading order, no overlap) decides which letter goes where.
    cands.sort(key=lambda m: -m.score)
    kept = []
    for m in cands:
        if all(k.letter != m.letter or _iou(m, k) < 0.3 for k in kept):
            kept.append(m)
    return kept


def _iou(a, b):
    ix = max(0, min(a.x1, b.x1) - max(a.x0, b.x0))
    iy = max(0, min(a.y1, b.y1) - max(a.y0, b.y0))
    inter = ix * iy
    union = (a.x1 - a.x0) * (a.y1 - a.y0) + (b.x1 - b.x0) * (b.y1 - b.y0) - inter
    return inter / union if union else 0.0


# --- 2. layout --------------------------------------------------------------------

def _follows(a, b):
    """True when marker b comes after marker a in reading order."""
    h = max(a.h, b.h)
    same_row = abs(a.cy - b.cy) < 0.5 * h
    return (same_row and b.x0 > a.x1) or b.cy > a.cy + 0.5 * h


def choose_layout(cands):
    """Pick the best A..E sequence. Letters that cannot be placed are left out.

    Score: sum of NCC scores, with a penalty for markers of different sizes. A
    sequence must respect reading order, and every marker must be about the same size.
    """
    by_letter = {L: [c for c in cands if c.letter == L] for L in LETTERS}
    best = (0.0, {})

    def extend(i, chosen, score):
        nonlocal best
        if score > best[0]:
            best = (score, dict(chosen))
        if i == len(LETTERS):
            return
        letter = LETTERS[i]
        # optimistic bound: every remaining letter scores 1
        if score + (len(LETTERS) - i) <= best[0]:
            return
        prev = chosen[max(chosen)] if chosen else None  # last placed letter
        for c in by_letter[letter]:
            if prev is not None and not _follows(prev, c):
                continue
            if chosen and not _same_size(c, chosen.values()):
                continue
            chosen[letter] = c
            extend(i + 1, chosen, score + c.score)
            del chosen[letter]
        # also allow this letter to be missing (a damaged or unusual marker)
        extend(i + 1, chosen, score)

    extend(0, {}, 0.0)
    return best[1]


def _same_size(c, others):
    hs = [o.h for o in others]
    ref = float(np.median(hs))
    return 0.8 * ref <= c.h <= 1.25 * ref


# --- 4. cells ------------------------------------------------------------------------

def _components(mask):
    """8-connected components of a small boolean grid -> list of (y0, x0, y1, x1)."""
    H, W = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    boxes = []
    ys, xs = np.nonzero(mask)
    for sy, sx in zip(ys, xs):
        if seen[sy, sx]:
            continue
        stack = [(sy, sx)]
        seen[sy, sx] = True
        y0 = y1 = sy
        x0 = x1 = sx
        while stack:
            y, x = stack.pop()
            y0, y1, x0, x1 = min(y0, y), max(y1, y), min(x0, x), max(x1, x)
            for ny in (y - 1, y, y + 1):
                if ny < 0 or ny >= H:
                    continue
                for nx in (x - 1, x, x + 1):
                    if 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        boxes.append((y0, x0, y1 + 1, x1 + 1))
    return boxes


def _rows_of(markers):
    rows = []
    for m in sorted(markers, key=lambda m: (m.cy, m.x0)):
        if rows and abs(rows[-1][0].cy - m.cy) < 0.5 * m.h:
            rows[-1].append(m)
        else:
            rows.append([m])
    return [sorted(r, key=lambda m: m.x0) for r in rows]


def find_cells(gray, markers):
    """One Cell per found marker."""
    H, W = gray.shape
    ink = gray < INK
    cells = {}
    for row in _rows_of(list(markers.values())):
        gaps = [b.x0 - a.x0 for a, b in zip(row, row[1:])]
        spacing = float(np.median(gaps)) if gaps else None
        for i, m in enumerate(row):
            h = m.h
            x_start = m.x1 + 1
            if i + 1 < len(row):
                x_end = row[i + 1].x0 - max(2, h // 6)
            elif spacing:
                x_end = min(W, int(m.x0 + 1.4 * spacing))
            else:
                x_end = W
            y_start = max(0, int(m.cy - 2.5 * h))
            y_end = min(H, int(m.cy + 2.5 * h))
            cells[m.letter] = _cell(gray, ink, m, x_start, x_end, y_start, y_end)
    return cells


def _cell(gray, ink, m, xa, xb, ya, yb):
    h = m.h
    if xb - xa < 2:
        return Cell(m.letter, "empty")
    win = ink[ya:yb, xa:xb]
    b = max(2, h // 10)  # block size: bridges the gaps inside a character or a digit pair
    gh, gw = -(-win.shape[0] // b), -(-win.shape[1] // b)
    padded = np.zeros((gh * b, gw * b), bool)
    padded[:win.shape[0], :win.shape[1]] = win
    grid = padded.reshape(gh, b, gw, b).any(axis=(1, 3))
    comps = [(y0 * b + ya, x0 * b + xa, min(y1 * b + ya, yb), min(x1 * b + xa, xb))
             for y0, x0, y1, x1 in _components(grid)]
    # the value sits on the marker's line: it crosses the band around the marker's centre
    band0, band1 = m.cy - 0.35 * h, m.cy + 0.35 * h
    on_line = [c for c in comps if c[0] < band1 and c[2] > band0]
    on_line.sort(key=lambda c: c[1])
    if not on_line or on_line[0][1] - m.x1 > 3.0 * h:
        return _figure_below(ink, m, xb) or Cell(m.letter, "empty")
    chain = [on_line[0]]
    for c in on_line[1:]:
        if c[1] - max(k[3] for k in chain) <= 1.0 * h:
            chain.append(c)
        else:
            break
    y0 = min(c[0] for c in chain)
    x0 = min(c[1] for c in chain)
    y1 = max(c[2] for c in chain)
    x1 = max(c[3] for c in chain)
    # Look for a bar at the mathematical axis before deciding which vertically
    # separated components belong to the value. A numerator can be farther than
    # the old 0.35*h component gap, and silently disappear from the crop.
    fraction = _fraction_at_axis(ink, x0, x1, h, m.cy)
    if fraction:
        box, parts = fraction
        return Cell(m.letter, "fraction", box, parts)
    # stacked pieces just above or below the line, inside its columns: the numerator
    # or denominator of a fraction whose bar is on the line
    for c in comps:
        if c in chain:
            continue
        overlap = min(c[3], x1) - max(c[1], x0)
        gap = max(c[0] - y1, y0 - c[2])
        # A genuine stack was handled above. Do not attach a preceding question
        # line to a normal digit (the top stroke of 7 used to become a bar).
        if (overlap >= 0.5 * (c[3] - c[1]) and gap <= 0.15 * h
                and c[2] - c[0] <= 1.0 * h):
            y0, y1 = min(y0, c[0]), max(y1, c[2])
    # tighten to the real ink (the grid rounds up to whole blocks)
    sub = ink[y0:y1, x0:x1]
    rows = np.nonzero(sub.any(1))[0]
    cols = np.nonzero(sub.any(0))[0]
    if len(rows) == 0:
        return Cell(m.letter, "empty")
    y0, y1 = y0 + rows[0], y0 + rows[-1] + 1
    x0, x1 = x0 + cols[0], x0 + cols[-1] + 1
    box = (int(x0), int(y0), int(x1), int(y1))
    height = (y1 - y0) / h
    if height <= FIGURE_HEIGHT:
        return Cell(m.letter, "text", box, [box])
    if height <= FRACTION_HEIGHT:
        parts = _split_fraction(ink, box, h, m.cy)
        if parts:
            return Cell(m.letter, "fraction", box, parts)
    return Cell(m.letter, "figure", box)


def _fraction_at_axis(ink, x0, x1, h, cy):
    """Find a separated numerator/bar/denominator at the marker's axis."""
    ya, yb = max(0, int(cy - 1.5 * h)), min(ink.shape[0], int(cy + 1.5 * h))
    sub = ink[ya:yb, x0:x1]
    if sub.size == 0 or x1 - x0 < 0.2 * h:
        return None
    rows = np.nonzero(sub.sum(1) >= 0.7 * (x1 - x0))[0]
    if not len(rows):
        return None
    runs = np.split(rows, np.nonzero(np.diff(rows) > 1)[0] + 1)
    for run in sorted(runs, key=lambda r: abs(ya + float(r.mean()) - cy)):
        top, bottom = int(run[0]), int(run[-1] + 1)
        if abs(ya + (top + bottom) / 2 - cy) > 0.23 * h or bottom - top > max(3, h / 6):
            continue
        occupied = sub.any(1)
        above, below = np.nonzero(occupied[:top])[0], np.nonzero(occupied[bottom:])[0] + bottom
        if not len(above) or not len(below):
            continue
        # A bar is isolated by white space on BOTH sides. A 7's top stroke or
        # a line inside a picture does not satisfy this condition.
        if not (0.10 * h <= top - above[-1] - 1 <= 0.65 * h
                and 0.10 * h <= below[0] - bottom <= 0.65 * h):
            continue
        # Keep the nearest line on each side, not any question text beyond it.
        breaks = np.nonzero(np.diff(above) > max(2, 0.15 * h))[0]
        if len(breaks):
            above = above[breaks[-1] + 1:]
        breaks = np.nonzero(np.diff(below) > max(2, 0.15 * h))[0]
        if len(breaks):
            below = below[:breaks[0] + 1]
        parts = []
        for occupied_rows in (above, below):
            a, b = int(occupied_rows[0]), int(occupied_rows[-1] + 1)
            cols = np.nonzero(sub[a:b].any(0))[0]
            if b - a < 0.2 * h or b - a > 1.2 * h:
                break
            parts.append((int(x0 + cols[0]), ya + a, int(x0 + cols[-1] + 1), ya + b))
        if len(parts) == 2:
            return (int(x0), parts[0][1], int(x1), parts[1][3]), parts
    return None


def _figure_below(ink, m, xb):
    """Layouts with the letter above its drawing: big ink right under the marker."""
    h = m.h
    H, W = ink.shape
    x0, x1 = max(0, int(m.x0 - h)), min(W, max(int(m.x1 + h), int(xb)))
    y0, y1 = int(m.y1), min(H, int(m.y1 + 4 * h))
    sub = ink[y0:y1, x0:x1]
    rows, cols = np.nonzero(sub.any(1))[0], np.nonzero(sub.any(0))[0]
    if len(rows) == 0 or rows[0] > 1.0 * h or rows[-1] - rows[0] < 1.0 * h:
        return None
    box = (int(x0 + cols[0]), int(y0 + rows[0]), int(x0 + cols[-1] + 1), int(y0 + rows[-1] + 1))
    return Cell(m.letter, "figure", box)


def _split_fraction(ink, box, h, cy):
    """Stacked fraction: a thin, wide bar with ink above and below it.

    Returns [numerator_box, denominator_box], or None if it is not a fraction.
    """
    x0, y0, x1, y1 = box
    sub = ink[y0:y1, x0:x1]
    width = x1 - x0
    fill = sub.sum(1) / max(1, width)
    bar_rows = np.nonzero(fill >= 0.7)[0]
    if len(bar_rows) == 0:
        return None
    # Runs of consecutive wide rows. Several can exist (the top stroke of a 7, a
    # minus sign); the bar is the thin run nearest the line centre with ink on both sides.
    runs = np.split(bar_rows, np.nonzero(np.diff(bar_rows) > 1)[0] + 1)
    best = None
    for run in runs:
        top, bottom = run[0], run[-1] + 1
        if bottom - top > max(3, h // 6):
            continue
        if sub[:top].sum() == 0 or sub[bottom:].sum() == 0:
            continue
        dist = abs((y0 + (top + bottom) / 2) - cy)
        if best is None or dist < best[0]:
            best = (dist, top, bottom)
    if best is None or best[0] > 0.5 * h:
        return None
    _, top, bottom = best
    num, den = sub[:top], sub[bottom:]

    def tight(part, oy):
        r = np.nonzero(part.any(1))[0]
        c = np.nonzero(part.any(0))[0]
        return (int(x0 + c[0]), int(y0 + oy + r[0]), int(x0 + c[-1] + 1), int(y0 + oy + r[-1] + 1))

    nb, db = tight(num, 0), tight(den, bottom)
    if (nb[3] - nb[1]) > 1.2 * h or (db[3] - db[1]) > 1.2 * h:
        return None
    return [nb, db]


# --- everything ---------------------------------------------------------------------

def segment(src, pad=None, templates=None):
    """Markers, answer zone and cells of one image."""
    gray = load_gray(src)
    markers = choose_layout(find_candidates(gray, templates))
    seg = Segmentation(markers=markers, missing=[L for L in LETTERS if L not in markers])
    if not markers:
        return seg
    seg.cells = find_cells(gray, markers)
    h = int(np.median([m.h for m in markers.values()]))
    pad = h // 2 if pad is None else pad
    xs0 = [m.x0 for m in markers.values()] + [c.box[0] for c in seg.cells.values() if c.box]
    ys0 = [m.y0 for m in markers.values()] + [c.box[1] for c in seg.cells.values() if c.box]
    xs1 = [m.x1 for m in markers.values()] + [c.box[2] for c in seg.cells.values() if c.box]
    ys1 = [m.y1 for m in markers.values()] + [c.box[3] for c in seg.cells.values() if c.box]
    H, W = gray.shape
    seg.zone = (max(0, min(xs0) - pad), max(0, min(ys0) - pad), min(W, max(xs1) + pad), min(H, max(ys1) + pad))
    return seg


def crop(src, box):
    gray = load_gray(src)
    x0, y0, x1, y1 = box
    return gray[y0:y1, x0:x1]
