"""Permutation-ensemble answering for Qwen3.5-2B (one letter, A to E).

What changes against the baseline (copilot.pipeline.solve), each measured on the 1747 English M3Kang problems:

1. Prompt: no system prompt, the question "Which option is correct?" after the options, and the answer
   started with "The correct option is ". The 2B answers almost always B with the baseline prompt.
2. Permutation ensemble (the "augmentation voting" of the ARC Prize winners): the five option values are
   shown in up to five cyclic orders; the log-probabilities of each value are summed over the orders, so the
   model's letter bias cancels out.
3. No options read (they are drawings, or OCR failed): answer D, the most common answer in train (25%).
   The model without options is below that.

Speed on the UNO Q: Qwen3.5 is a hybrid (DeltaNet) model, so llama-server cannot reuse a cached prefix
unless a checkpoint sits exactly there. We send the shared part (the question) once, which leaves a
checkpoint at its end, and each order then only reads its options. Start llama-server with
--ctx-checkpoints 8 or more, so the question's checkpoint is not evicted by the orders.
The number of orders is chosen from the token count before starting (deterministic), so the
estimated board time stays under the limit.
"""
import math
import socket
import time
import urllib.error

from .client import post
from .config import CONFIG

LETTERS = "ABCDE"
URL = f"http://127.0.0.1:{CONFIG['LLM_PORT']}"
TIME_LIMIT = float(CONFIG["TIME_LIMIT_SECONDS"])
FALLBACK = CONFIG["FALLBACK_ANSWER"]
PREFILL_TPS = float(CONFIG.get("PERM_PREFILL_TPS", "7.0"))  # 2B Q4_0 with the A53 GEMM kernel: 7.5 measured
BUDGET = float(CONFIG.get("PERM_BUDGET_SECONDS", "48"))     # at 7.0 tok/s; measured max 46 s on the board (54 -> 53 s)
MAX_ORDERS = int(CONFIG.get("PERM_MAX_ORDERS", "5"))
SHIFTS = (0, 2, 4, 1, 3)  # spread out: the first three already cover very different positions
OVERHEAD = 0.6  # seconds per request: one decoded letter, HTTP, sampling

PREFIX = "<|im_start|>user\n"
SUFFIX = ("\n\nWhich option is correct?<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
          "The correct option is ")


def has_five(problem):
    options = problem.get("options") or {}
    return all(options.get(l) not in (None, "") for l in LETTERS)


def order(shift):
    return LETTERS[shift:] + LETTERS[:shift]


def shared_part(problem):
    return PREFIX + problem["text"].strip() + "\n"


def order_part(problem, shift):
    options = problem["options"]
    return "\n".join(f"{shown}) {options[orig]}" for shown, orig in zip(LETTERS, order(shift))) + SUFFIX


def n_tokens(text, url, timeout):
    return len(post(url + "/tokenize", {"content": text}, timeout)["tokens"])


def letter_probs(prompt, url, timeout):
    d = post(url + "/completion", {
        "prompt": prompt, "grammar": "root ::= [A-E]", "n_predict": 1,
        "temperature": 1, "top_k": 0, "top_p": 1, "min_p": 0, "n_probs": 5, "post_sampling_probs": True,
        "seed": int(CONFIG["SEED"]), "cache_prompt": True}, timeout)
    probs = {l: 1e-9 for l in LETTERS}
    for t in d["completion_probabilities"][0]["top_probs"]:
        if t["token"] in probs:
            probs[t["token"]] = max(t["prob"], 1e-9)
    return probs, d.get("timings", {})


def plan_orders(shared_n, order_n):
    """How many orders fit in the budget, from the token counts only."""
    k = 0
    for k_try in range(1, MAX_ORDERS + 1):
        if (shared_n + k_try * order_n) / PREFILL_TPS + (k_try + 1) * OVERHEAD > BUDGET:
            break
        k = k_try
    return max(k, 1)


def solve(problem, url=URL, time_limit=TIME_LIMIT):
    start = time.perf_counter()
    result = {"answer": FALLBACK, "status": "ok", "prompt_tokens": 0, "generated_tokens": 0, "orders": 0}
    if not has_five(problem):
        result["seconds"] = 0.0
        return result
    try:
        shared = shared_part(problem)
        shared_n = n_tokens(shared, url, 10)
        order_n = n_tokens(order_part(problem, 0), url, 10)
        k = plan_orders(shared_n, order_n)
        # Warm the shared part once: llama-server leaves a checkpoint at its end.
        post(url + "/completion", {"prompt": shared, "n_predict": 1, "temperature": 0, "cache_prompt": True,
                                   "seed": int(CONFIG["SEED"])}, time_limit)
        result["prompt_tokens"] += shared_n
        result["generated_tokens"] += 1
        score = {l: 0.0 for l in LETTERS}
        for shift in SHIFTS[:k]:
            remaining = time_limit - (time.perf_counter() - start) - 2.0
            if remaining < order_n / PREFILL_TPS + OVERHEAD and result["orders"]:
                break  # safety net only: the plan above should never get here
            probs, timings = letter_probs(shared + order_part(problem, shift), url, max(remaining, 1.0))
            for shown, orig in zip(LETTERS, order(shift)):
                score[orig] += math.log(probs[shown])
            result["orders"] += 1
            result["prompt_tokens"] += timings.get("prompt_n", order_n)
            result["generated_tokens"] += 1
        result["answer"] = max(LETTERS, key=lambda l: (score[l], -LETTERS.index(l)))
    except (socket.timeout, TimeoutError):
        result["status"] = "timeout"
    except urllib.error.URLError as error:
        result["status"] = "timeout" if isinstance(error.reason, (socket.timeout, TimeoutError)) else \
            f"error: {error.reason}"
    result["seconds"] = round(time.perf_counter() - start, 2)
    return result
