"""Reasoning solver used by pipeline.solve (predict.py and eval.py).

Text problems : one short line of reasoning, then a forced letter (GBNF grammar).
                The generation budget is computed from the time left for THIS problem,
                using the board's measured reading/writing speeds in config.env.
                If the budget runs out before the letter, one cheap 1-token letter call
                reuses the cached prompt. If even that does not fit, the fallback letter.
Figure problems: the original page image goes to the vision server (Qwen3.5-0.8B + mmproj),
                 one forced letter. Without a vision server, or without the image, they go
                 through the text route (the status says so), never silently.
Everything is deterministic: temperature 0, fixed seed.
"""
import base64
import re
import time
from pathlib import Path

from .client import get, post
from .config import CONFIG

LETTERS = "ABCDE"
SEED = int(CONFIG.get("SEED", 42))
SYSTEM = "You are an expert at Kangaroo math competition problems. Exactly one option is correct."
INSTRUCTION = "Think briefly in one line (compute the key quantity), then give the letter."
MAX_CHARS = int(CONFIG.get("REASON_MAX_CHARS", 350))
# Board speeds of the TEXT model (tokens/s). Defaults: Qwen3-1.7B Q4_K_M projected from the
# README's 0.8B measurements (11 read / 5.9 write) and our laptop ratios (1.95x / 1.31x).
READ_TPS = float(CONFIG.get("LLM_READ_TPS", 5.6))
WRITE_TPS = float(CONFIG.get("LLM_WRITE_TPS", 4.5))
REASON_MIN_TOKENS = 40          # below this, reasoning is pointless: answer with one letter


def format_problem(problem):
    lines = [problem["text"].strip()]
    options = problem.get("options") or {}
    for letter in LETTERS:
        if options.get(letter):
            lines.append(f"{letter}) {options[letter]}")
    if not any(options.get(l) for l in LETTERS):
        lines.append("(The options are in a picture. Pick the most likely letter A-E.)")
    return "\n".join(lines)


def estimate_tokens(text):
    return 30 + len(text) / 3.6       # chat template + roughly 3.6 characters per token


def _letter_from(text):
    tail = text.rsplit("Answer:", 1)[-1].strip()
    return tail[:1] if tail[:1] in LETTERS else None


def solve_text(problem, url, deadline):
    """Return (letter or None, status, info)."""
    user = format_problem(problem) + "\n\n" + INSTRUCTION
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    remaining = deadline - time.perf_counter()
    read_s = estimate_tokens(SYSTEM + user) / READ_TPS
    budget = int((remaining - read_s - 2.0) * WRITE_TPS)
    info = {"budget": budget}
    if budget < REASON_MIN_TOKENS:
        return _letter_only(messages, url, deadline, info, "short_budget")
    # Cap the reasoning line in CHARACTERS from the token budget (2.2 chars/token, conservative) so the model always
    # reaches "Answer: X" inside this call. The fallback call below re-reads the whole conversation on hybrid
    # (linear-attention) models such as Qwen3.5, whose recurrent state cannot reuse the prompt cache.
    max_chars = max(10, min(MAX_CHARS, int((budget - 8) * 2.2)))   # 2.2 chars/token: Catalan/math lines measured 2.2-2.6
    info["max_chars"] = max_chars
    grammar = 'root ::= "Reasoning: " line "\\nAnswer: " [A-E]\nline ::= [^\\n]{10,%d}' % max_chars
    # Raw completion on the server-rendered prompt: if the budget runs out, the fallback continues EXACTLY the same
    # text, so the server reuses its cache and reads only "\nAnswer: ". (A chat-style follow-up re-renders the
    # earlier answer without its empty <think> block and re-reads all the reasoning: ~20 s on the board.)
    base = url.split("/v1/")[0]
    prompt = post(base + "/apply-template", {"messages": messages},
                  timeout=max(1.0, deadline - time.perf_counter()))["prompt"]
    r = post(base + "/completion", {"prompt": prompt, "grammar": grammar, "n_predict": min(budget, 220),
                                    "temperature": 0, "seed": SEED, "cache_prompt": True},
             timeout=max(1.0, deadline - time.perf_counter()))
    out = r["content"]
    info.update(prompt_tokens=r.get("timings", {}).get("prompt_n", 0),
                generated=r.get("timings", {}).get("predicted_n", 0))
    letter = _letter_from(out) if "\nAnswer:" in out else None
    if letter:
        return letter, "ok", info
    if deadline - time.perf_counter() < 3.0:
        return None, "truncated_no_time", info
    reasoning = out.split("\nAnswer:", 1)[0]
    r = post(base + "/completion", {"prompt": prompt + reasoning + "\nAnswer: ", "grammar": "root ::= [A-E]",
                                    "n_predict": 1, "temperature": 0, "seed": SEED, "cache_prompt": True},
             timeout=max(1.0, deadline - time.perf_counter()))
    t = r.get("timings", {})
    info["prompt_tokens"] = info.get("prompt_tokens", 0) + t.get("prompt_n", 0)
    info["generated"] = info.get("generated", 0) + t.get("predicted_n", 0)
    letter = r["content"].strip()[:1]
    return (letter if letter in LETTERS else None), "truncated_letter", info


def _letter_only(messages, url, deadline, info, why):
    if deadline - time.perf_counter() < 3.0:
        return None, why + "_no_time", info
    msgs = messages + [{"role": "user", "content": "Reply with the letter of the correct option only."}]
    r = post(url, {"messages": msgs, "grammar": "root ::= [A-E]", "max_tokens": 1, "temperature": 0,
                   "seed": SEED, "cache_prompt": True}, timeout=max(1.0, deadline - time.perf_counter()))
    letter = r["choices"][0]["message"]["content"].strip()[:1]
    # count the fallback call too (its uncached prompt tokens + 1 generated token) for timing reports
    t = r.get("timings", {})
    info["prompt_tokens"] = info.get("prompt_tokens", 0) + t.get("prompt_n", 0)
    info["generated"] = info.get("generated", 0) + t.get("predicted_n", 0)
    return (letter if letter in LETTERS else None), why + "_letter", info


def find_page_image(problem, image_root):
    """The organisers' prepare_m3kang.py --save-images writes images/<id>_<language>.png next to the jsonl.
    Also accept an explicit source_image field. Paths must stay inside image_root."""
    if not image_root:
        return None
    root = Path(image_root).resolve()
    candidates = []
    if problem.get("source_image"):
        candidates.append(problem["source_image"])
    lang = problem.get("language") or "eng"
    candidates += [f"images/{problem['id']}_{lang}.png", f"images/{problem['id']}.png"]
    for rel in candidates:
        path = (root / rel).resolve()
        if path.is_relative_to(root) and path.is_file():
            return path
    return None


_vision_alive = {}


def vision_available(url):
    if not url:
        return False
    if url not in _vision_alive:
        health = url.split("/v1/")[0] + "/health"
        try:
            _vision_alive[url] = get(health, timeout=2).get("status") == "ok"
        except Exception:
            _vision_alive[url] = False
    return _vision_alive[url]


def solve_vision(problem, image_path, url, deadline):
    raw = image_path.read_bytes()
    mime = "image/png" if raw.startswith(b"\x89PNG") else "image/jpeg"
    text = format_problem(problem) + ("\nThe image shows the whole problem with its figure and the options A-E. "
                                      "Reply with the letter of the correct option.")
    content = [{"type": "image_url", "image_url": {"url": f"data:{mime};base64," + base64.b64encode(raw).decode()}},
               {"type": "text", "text": text}]
    r = post(url, {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}],
                   "grammar": "root ::= [A-E]", "max_tokens": 1, "temperature": 0, "seed": SEED},
             timeout=max(1.0, deadline - time.perf_counter()))
    letter = r["choices"][0]["message"]["content"].strip()[:1]
    return (letter if letter in LETTERS else None), "vision", {"prompt_tokens": r.get("timings", {}).get("prompt_n", 0)}


def is_figure_problem(problem):
    return problem.get("text_only") is False or bool(problem.get("requires_vision"))
