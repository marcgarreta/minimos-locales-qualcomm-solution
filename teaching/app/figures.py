"""Figures and answer pictures of a problem, with the team's OCR pipeline (ocr_handoff/).

The web shows the statement as TEXT, so the picture must not repeat it. The team's pipeline
(answer_zone + src/export_multimodal.py, vendored unchanged in ocr_handoff/) cuts each page into:

- the diagram with its nearby labels ("question.png"), without the paragraph of the statement;
- one crop per option when the options are pictures (or unreadable), with the A) marker removed;
- the A-E option text read by OCR, repaired with the statement's vocabulary;
- and, when the separation is uncertain, an explicit fallback to the original page.

The bank's results are precomputed on the laptop (seed/build_figures.py -> seed/figures.json).
A photo added by the teacher goes through the same code on the board (Pipeline.process), when its
dependencies are there (numpy, Pillow, OpenCV, onnxruntime); otherwise the photo is shown as is.
"""
import hashlib
import io
import sys
import threading
from pathlib import Path

PLACEHOLDER = "[see option"


def describe(row, prefix):
    """The pipeline's row -> what the app stores: paths are made relative to `prefix`."""
    def rel(asset):
        return f"{prefix}/{asset['path']}".replace("\\", "/") if asset else None

    images = row.get("images") or []
    figure = next((a for a in images if a["role"] in ("diagram", "problem")), None)
    options = {a["letter"]: rel(a) for a in images if a["role"] == "option"}
    texts = {k: v for k, v in (row.get("options") or {}).items() if v and not v.startswith(PLACEHOLDER)}
    return {"figure": rel(figure), "fallback": bool(figure and figure["role"] == "problem"),
            "options": options if len(options) == 5 else {}, "texts": texts,
            "mode": row.get("image_mode", "text")}


class Pipeline:
    """Loads the vendored pipeline once; process() runs it on one picture (thread-safe, one at a time)."""

    def __init__(self, root):
        self.root = Path(root)
        self.error = None
        self._mods = None
        self._lock = threading.Lock()

    def _load(self):
        if self._mods or self.error:
            return
        try:
            for p in (self.root / "src", self.root / "minimos-locales-qualcomm"):
                if str(p) not in sys.path:
                    sys.path.insert(0, str(p))
            import export_multimodal as em
            from answer_zone import extract, load_recognizer
            self._mods = (em, extract, load_recognizer("onnx", threads=2))
        except Exception as e:  # noqa: BLE001  (onnxruntime / cv2 missing, model missing...)
            self.error = f"{type(e).__name__}: {e}"

    @property
    def available(self):
        self._load()
        return self._mods is not None

    def read_options(self, image_bytes):
        """Just the A-E option text (for the teacher's form)."""
        self._load()
        if not self._mods:
            return {"available": False, "error": self.error, "options": {}}
        _, extract, rec = self._mods
        with self._lock:
            r = extract(image_bytes, recognizer=rec)
        return {"available": True, "ok": r.ok, "options": r.values(), "problems": r.problems}

    def process(self, pid, image_bytes, text, level, answer, data_dir):
        """Run the pipeline on one photo. Writes data_dir/images/<pid>.png and data_dir/multimodal/<pid>/;
        returns describe(row) with paths relative to data_dir's parent folder name."""
        self._load()
        if not self._mods:
            return None
        em, extract, rec = self._mods
        from PIL import Image
        data = Path(data_dir)
        (data / "images").mkdir(parents=True, exist_ok=True)
        path = data / "images" / f"{pid}.png"
        Image.open(io.BytesIO(image_bytes)).convert("RGB").save(path)
        problem = {"id": pid, "level": level, "text_only": False, "text_eng": text or "", "label": answer}
        with self._lock:
            extraction = extract(str(path), recognizer=rec).to_dict()
            extraction.update(id=pid, image_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            row = em.export_record(problem, extraction, data)
        return describe(row, data.name)
