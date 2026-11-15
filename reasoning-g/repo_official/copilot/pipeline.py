"""The baseline copilot: one problem in, one letter out.

This is the file to change first. predict.py and eval.py both call solve(),
so whatever you build here is exactly what the official run measures.
"""
import socket
import time
import urllib.error

from .config import CONFIG
from .llm import URL, answer_letter
from .images import load_image_parts, needs_vision

TIME_LIMIT = float(CONFIG["TIME_LIMIT_SECONDS"])
FALLBACK = CONFIG["FALLBACK_ANSWER"]
MARGIN = 3.0  # seconds kept free for Python and for writing the answer


def baseline_solve(problem, index=None, k=0, exclude_id=None, image_b64=None, llm_url=URL,
          time_limit=TIME_LIMIT, image_root=None, vision_url=None, image_mode="separate"):
    """Return {"answer", "seconds", "status", ...} for one problem.

    index and k turn on retrieval: the k most similar solved problems are
    added to the prompt as examples. Each example costs reading time.
    image_b64 and llm_url send the problem image to a vision server.
    Batch inputs can instead provide images[] relative to image_root. Only
    visual problems use vision_url; text-only problems keep the text server.
    """
    start = time.perf_counter()
    result = {"answer": FALLBACK, "status": "ok", "prompt_tokens": 0, "retrieved": "", "examples": [],
              "images_sent": 0}
    image_parts = None
    if needs_vision(problem) and not image_b64:
        if not vision_url:
            result.update(status="vision_unavailable", seconds=round(time.perf_counter() - start, 2))
            return result
        try:
            if image_root is None:
                raise ValueError("image_root is required for local image attachments")
            image_parts = load_image_parts(problem, image_root, image_mode)
        except (OSError, ValueError, KeyError, TypeError) as error:
            result.update(status="image_error: " + str(error), seconds=round(time.perf_counter() - start, 2))
            return result
        llm_url = vision_url
    try:
        examples = []
        if index is not None and k > 0:
            hits = index.search(problem, k=k, exclude_id=exclude_id)
            examples = [p for _score, p in hits]
            result["examples"] = hits
            result["retrieved"] = ";".join(f"{p['id']}:{s:.2f}" for s, p in hits)
        remaining = time_limit - (time.perf_counter() - start) - MARGIN
        if remaining <= 0:
            result.update(status="timeout", seconds=round(time.perf_counter() - start, 2))
            return result
        result["images_sent"] = (sum(p["type"] == "image_url" for p in image_parts)
                                 if image_parts else int(bool(image_b64)))
        letter, timings = answer_letter(problem, examples, timeout=max(remaining, 1.0),
                                        image_b64=image_b64, url=llm_url, image_parts=image_parts)
        result["answer"] = letter
        result["prompt_tokens"] = timings.get("prompt_n", 0)
    except (socket.timeout, TimeoutError):
        result["status"] = "timeout"
    except urllib.error.URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            result["status"] = "timeout"
        else:
            result["status"] = f"error: {error.reason}"
    result["seconds"] = round(time.perf_counter() - start, 2)
    return result


# --------------------------------------------------------------------------------------------
# Reasoning solver (default). SOLVER=baseline in config.env restores the one-letter baseline.
# --------------------------------------------------------------------------------------------
from . import solver as S  # noqa: E402

SOLVER = CONFIG.get("SOLVER", "reason")
VISION_URL = CONFIG.get("VISION_URL") or f"http://127.0.0.1:{CONFIG.get('VISION_PORT', '8083')}/v1/chat/completions"
DEADLINE_MARGIN = float(CONFIG.get("DEADLINE_MARGIN_SECONDS", 5.0))


def solve(problem, index=None, k=0, exclude_id=None, image_b64=None, llm_url=URL,
          time_limit=TIME_LIMIT, image_root=None, vision_url=None, image_mode="separate"):
    """One problem in, {"answer", "seconds", "status", ...} out, always within time_limit."""
    # explicit multi-image manifests (src/export_multimodal.py "images" field) keep the tested multimodal path;
    # the organisers' prepared rows have no "images" field and use the reasoning solver below.
    if SOLVER == "baseline" or k or image_b64 or problem.get("images"):
        return baseline_solve(problem, index, k, exclude_id, image_b64, llm_url, time_limit, image_root,
                              vision_url or (VISION_URL if SOLVER != "baseline" and problem.get("images")
                                             and S.vision_available(VISION_URL) else None),
                              image_mode)
    start = time.perf_counter()
    deadline = start + time_limit - DEADLINE_MARGIN
    result = {"answer": FALLBACK, "status": "ok", "prompt_tokens": 0, "retrieved": "", "examples": [],
              "images_sent": 0}
    vurl = vision_url or VISION_URL
    try:
        letter, status, info = None, "", {}
        if S.is_figure_problem(problem):
            if problem.get("images") and image_root and S.vision_available(vurl):
                # explicit multi-image attachments (src/export_multimodal.py manifests)
                parts = load_image_parts(problem, image_root, image_mode)
                letter, timings = answer_letter(problem, (), timeout=max(1.0, deadline - time.perf_counter()),
                                                url=vurl, image_parts=parts)
                status, info = "vision_attachments", {"prompt_tokens": timings.get("prompt_n", 0)}
                result["images_sent"] = sum(p["type"] == "image_url" for p in parts)
            else:
                page = S.find_page_image(problem, image_root)
                if page is not None and S.vision_available(vurl):
                    letter, status, info = S.solve_vision(problem, page, vurl, deadline)
                    result["images_sent"] = 1
                else:
                    letter, status, info = S.solve_text(problem, llm_url, deadline)
                    status = ("figure_no_image_" if page is None else "figure_no_vision_") + status
        else:
            letter, status, info = S.solve_text(problem, llm_url, deadline)
        result["status"] = status
        result["prompt_tokens"] = info.get("prompt_tokens", 0)
        result["generated_tokens"] = info.get("generated", 0)
        if letter and letter in S.LETTERS:          # letter is None when no answer was produced in time
            result["answer"] = letter
        else:
            result["status"] = status + "_fallback"
    except (socket.timeout, TimeoutError):
        result["status"] = "timeout_fallback"
    except urllib.error.URLError as error:
        result["status"] = ("timeout_fallback" if isinstance(error.reason, (socket.timeout, TimeoutError))
                            else f"error_fallback: {error.reason}")
    except Exception as error:   # never crash the official run: answer the fallback letter
        result["status"] = f"error_fallback: {type(error).__name__}: {error}"[:200]
    result["seconds"] = round(time.perf_counter() - start, 2)
    return result
