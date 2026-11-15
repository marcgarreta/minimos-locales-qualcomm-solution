"""Debug pictures: the image with the markers, cells and answer zone drawn on it.

Blue: markers A) .. E). Green: text value. Orange: fraction. Red: figure / failed.
Magenta: the answer zone (the crop from A) to the end of E), plus the margin).
"""
from PIL import Image, ImageDraw

from .segment import load_gray

COLORS = {"text": (0, 160, 60), "fraction": (230, 130, 0), "figure": (220, 0, 0),
          "empty": (220, 0, 0), "missing": (220, 0, 0)}


def _font(size):
    """A TrueType font with ², √ (DejaVu on Debian, Arial on Windows), else Pillow's."""
    from PIL import ImageFont
    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def draw(src, result):
    img = Image.fromarray(load_gray(src)).convert("RGB")
    d = ImageDraw.Draw(img)
    if result.zone:
        d.rectangle(result.zone, outline=(200, 0, 200), width=3)
    for L, o in result.options.items():
        if o.marker_box:
            d.rectangle(o.marker_box, outline=(0, 90, 230), width=2)
        if o.box:
            color = COLORS["figure"] if L in result.problems else COLORS.get(o.kind, (0, 0, 0))
            d.rectangle(o.box, outline=color, width=2)
    return img


def panel(src, result, title=""):
    """Annotated image, the zone crop below it, and the values read, in one picture."""
    full = draw(src, result)
    gray = load_gray(src)
    parts = [full]
    if result.zone:
        x0, y0, x1, y1 = result.zone
        parts.append(Image.fromarray(gray[y0:y1, x0:x1]).convert("RGB"))
    lines = [title] if title else []
    for L, o in result.options.items():
        if L in result.problems:
            lines.append(f"{L}) ERROR: {result.problems[L]}")
        else:
            lines.append(f"{L}) {o.value!r}   [{o.kind}, conf {o.confidence:.2f}]")
    lines += [f"warning: {w}" for w in result.warnings]
    lines.append("time: " + ", ".join(f"{k} {v * 1000:.0f} ms" for k, v in result.seconds.items()))
    line_h = 22
    text = Image.new("RGB", (full.width, line_h * len(lines) + 10), "white")
    td = ImageDraw.Draw(text)
    font = _font(18)
    for i, line in enumerate(lines):
        color = (200, 0, 0) if "ERROR" in line else (0, 0, 0)
        td.text((10, 5 + i * line_h), line, fill=color, font=font)
    parts.append(text)
    W = max(p.width for p in parts)
    H = sum(p.height for p in parts) + 10 * (len(parts) - 1)
    out = Image.new("RGB", (W, H), (235, 235, 235))
    y = 0
    for p in parts:
        out.paste(p, (0, y))
        y += p.height + 10
    return out
