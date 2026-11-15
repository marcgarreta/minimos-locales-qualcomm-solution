"""Read the options A) .. E) from a problem photo with minimos-locales-qualcomm/answer_zone.

Optional: needs numpy + Pillow (+ onnxruntime or tesseract). When they are missing, the
teacher just types the options and `available()` is False.
"""
import sys

_extract = None
_error = None


def _load(path):
    global _extract, _error
    if _extract or _error:
        return
    try:
        if path not in sys.path:
            sys.path.insert(0, path)
        from answer_zone import extract, load_recognizer
        rec = load_recognizer("auto")
        _extract = lambda data: extract(data, recognizer=rec)  # noqa: E731
    except Exception as e:  # ImportError, OCRUnavailable, missing model...
        _error = f"{type(e).__name__}: {e}"


def available(path):
    _load(path)
    return _extract is not None


def read_options(path, image_bytes):
    _load(path)
    if not _extract:
        return {"available": False, "error": _error, "options": {}}
    r = _extract(image_bytes)
    return {"available": True, "ok": r.ok, "options": r.values(), "problems": r.problems}
