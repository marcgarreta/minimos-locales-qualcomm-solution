"""Load explicit local image attachments; never infer assets from a problem ID."""
import base64
from pathlib import Path


def needs_vision(problem):
    return bool(problem.get("requires_vision") or problem.get("images"))


def load_image_parts(problem, image_root, image_mode="separate"):
    root = Path(image_root).resolve()
    parts = []
    assets = problem.get("images") or []
    if image_mode not in ("original", "separate", "grouped", "panel"):
        raise ValueError("image mode must be original, separate, grouped or panel")
    if image_mode == "original":
        if not problem.get("source_image"):
            raise ValueError("original image mode requires source_image")
        assets = [problem["source_image"]]
    if image_mode == "grouped" and problem.get("answer_panel"):
        assets = [a for a in assets if a["role"] != "option"] + [problem["answer_panel"]]
    if image_mode == "panel" and problem.get("image_panel"):
        assets = [problem["image_panel"]]
    if not assets:
        raise ValueError("visual problem has no image attachments")
    for asset in assets:
        relative = Path(asset["path"])
        path = (root / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(root):
            raise ValueError("image path must stay inside the image root")
        role = asset.get("role")
        if role == "option" and asset.get("letter") in tuple("ABCDE"):
            caption = asset["letter"] + ")"
        elif role == "problem":
            caption = ("Original problem image, including diagrams and labeled choices. "
                       "Use this original if a separate option crop is incomplete:")
        elif role == "diagram":
            caption = "Question diagram"
        elif role == "panel":
            caption = "Visual panel"
        elif role == "answers":
            caption = "Answer choices A), B), C), D), E)"
        else:
            raise ValueError("unknown image role or option letter")
        raw = path.read_bytes()
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif raw.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        else:
            raise ValueError("image must be a PNG or JPEG")
        parts.append({"type": "text", "text": caption})
        parts.append({"type": "image_url", "image_url": {
            "url": "data:" + mime + ";base64," + base64.b64encode(raw).decode("ascii")}})
    return parts
