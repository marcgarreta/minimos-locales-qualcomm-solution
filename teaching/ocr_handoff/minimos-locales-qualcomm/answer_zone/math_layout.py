"""Small image-layout helpers for math structure that line OCR cannot preserve."""
import numpy as np

from .segment import INK


def power_parts(gray, box, marker):
    """Separate visibly raised glyphs from the baseline, in reading order.

    Character identity still comes from OCR; position supplies only the exponent
    relationship. Small dots and degree marks are excluded by their ink height.
    """
    x0, y0, x1, y1 = box
    ink = gray[y0:y1, x0:x1] < INK
    cols = np.nonzero(ink.any(0))[0]
    if not len(cols):
        return [("text", box)]
    runs = np.split(cols, np.nonzero(np.diff(cols) > 1)[0] + 1)
    groups = []
    for run in runs:
        a, b = int(run[0]), int(run[-1] + 1)
        rows = np.nonzero(ink[:, a:b].any(1))[0]
        top, bottom = int(rows[0]), int(rows[-1] + 1)
        raised = bottom + y0 <= marker.cy + 0.05 * marker.h and bottom - top >= 0.30 * marker.h
        kind = "power" if raised else "text"
        if groups and groups[-1][0] == kind:
            groups[-1][2] = b
        else:
            groups.append([kind, a, b])
    if not any(g[0] == "power" for g in groups):
        return [("text", box)]
    # A line beginning with a raised character has no unambiguous base.
    if groups[0][0] == "power":
        return [("text", box)]
    parts = []
    for kind, a, b in groups:
        rows = np.nonzero(ink[:, a:b].any(1))[0]
        parts.append((kind, (x0 + a, y0 + int(rows[0]), x0 + b, y0 + int(rows[-1] + 1))))
    return parts


def fraction_value(numerator, denominator):
    """Serialize stacked math without changing operator precedence."""
    def group(value):
        # Keep atomic numeric/simple-symbol fractions compact. Parenthesize
        # sums, differences and nested division on either side of the bar.
        return "(" + value + ")" if any(c in value[1:] for c in "+-/") else value
    return group(numerator) + "/" + group(denominator)
