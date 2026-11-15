"""Single-line text recognition for the answer cells.

The options that matter (numbers, words, short formulas) are always on one line,
so there is no text *detection* step: the segmenter already knows where every
cell is, and the recognizer only reads one line per cell. That keeps the cost on
the UNO Q to one small CRNN pass per option.

Backends:

* ``OnnxLineRecognizer`` (default): PP-OCRv4 recognition model (Apache 2.0, the
  same one RapidOCR uses) run with onnxruntime. Needs ``numpy``, ``Pillow`` and
  ``onnxruntime``. No OpenCV. The character list is stored inside the ONNX file.
* ``TesseractLineRecognizer``: calls ``tesseract --psm 7`` (single text line)
  through ``subprocess``. Installable on the board with apt only
  (``sudo apt-get install tesseract-ocr``), no pip at all.
"""
import os
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL = os.path.join(HERE, "models", "ch_PP-OCRv4_rec_infer.onnx")


class OCRUnavailable(RuntimeError):
    """No OCR backend could be loaded (missing model file or library)."""


def _to_gray(img):
    if isinstance(img, Image.Image):
        img = np.asarray(img.convert("L"))
    return np.asarray(img, dtype=np.uint8)


def _pad(gray, px):
    """White border around a tight crop: both backends read better with margin."""
    return np.pad(gray, px, mode="constant", constant_values=255)


class OnnxLineRecognizer:
    name = "onnx-ppocrv4"

    def __init__(self, model_path=DEFAULT_MODEL, threads=4, height=48):
        try:
            import onnxruntime as ort
        except ImportError as e:  # pragma: no cover - depends on the machine
            raise OCRUnavailable("onnxruntime is not installed") from e
        if not os.path.exists(model_path):
            raise OCRUnavailable(f"OCR model not found: {model_path} (run answer_zone/tools/fetch_model.py)")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(model_path, sess_options=opts, providers=["CPUExecutionProvider"])
        chars = self.session.get_modelmeta().custom_metadata_map["character"].splitlines()
        # CTC: index 0 is the blank, and PaddleOCR appends a space at the end.
        self.chars = ["<blank>"] + chars + [" "]
        self.input_name = self.session.get_inputs()[0].name
        self.height = height

    def _prepare(self, gray, width):
        h, w = gray.shape
        new_w = max(1, min(width, int(np.ceil(self.height * w / h))))
        img = Image.fromarray(gray).resize((new_w, self.height), Image.BILINEAR)
        x = np.asarray(img, dtype=np.float32) / 255.0
        x = (x - 0.5) / 0.5
        out = np.zeros((3, self.height, width), dtype=np.float32)  # zero = mid-grey padding, as PaddleOCR
        out[:, :, :new_w] = x[None]
        return out

    def _decode(self, probs):
        idx = probs.argmax(axis=1)
        conf = probs.max(axis=1)
        text, scores, prev = [], [], -1
        for i, c in zip(idx, conf):
            if i != prev and i != 0:
                text.append(self.chars[i] if i < len(self.chars) else "")
                scores.append(float(c))
            prev = i
        return "".join(text), (float(np.mean(scores)) if scores else 0.0)

    def read_lines(self, crops):
        """Read a list of single-line grayscale crops. Returns [(text, score)]."""
        if not crops:
            return []
        grays = [_pad(_to_gray(c), 6) for c in crops]
        ratios = [g.shape[1] / g.shape[0] for g in grays]
        width = int(np.ceil(self.height * max(max(ratios), 320 / 48)))
        batch = np.stack([self._prepare(g, width) for g in grays])
        preds = self.session.run(None, {self.input_name: batch})[0]
        return [self._decode(p) for p in preds]


class TesseractLineRecognizer:
    name = "tesseract-psm7"

    def __init__(self, binary="tesseract", lang="eng"):
        self.binary = shutil.which(binary)
        if not self.binary:
            raise OCRUnavailable("tesseract is not installed (sudo apt-get install tesseract-ocr)")
        self.lang = lang

    def read_lines(self, crops):
        results = []
        for c in crops:
            gray = _pad(_to_gray(c), 10)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                path = f.name
            try:
                Image.fromarray(gray).save(path)
                out = subprocess.run([self.binary, path, "stdout", "--psm", "7", "-l", self.lang],
                                     capture_output=True, text=True, timeout=20)
                results.append((out.stdout.strip(), 1.0 if out.stdout.strip() else 0.0))
            finally:
                os.unlink(path)
        return results


def load_recognizer(backend="auto", **kwargs):
    """``auto`` tries onnxruntime first, then tesseract."""
    errors = []
    order = {"auto": ["onnx", "tesseract"], "onnx": ["onnx"], "tesseract": ["tesseract"]}[backend]
    for name in order:
        try:
            return OnnxLineRecognizer(**kwargs) if name == "onnx" else TesseractLineRecognizer()
        except OCRUnavailable as e:
            errors.append(str(e))
    raise OCRUnavailable("; ".join(errors))
