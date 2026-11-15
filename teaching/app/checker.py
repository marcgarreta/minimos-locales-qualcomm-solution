"""Calculation checker: marks the numbers in a student's written solution that the LLM finds surprising.

How it works (see experiments/ppl in the datathon folder):
the Qwen3.5 0.8B llama-server reads the problem, the correct answer and the student's text, and we take
-log p(token) for every token by teacher forcing (a grammar that forces the exact token ids). Only DIGIT tokens
count: unusual words are also surprising, but a wrong result (e.g. "7 x 8 = 54") is surprising to the model because
it would have written another number. On solutions written by another model, a digit with NLL > 5 nats caught 80%
of calculation slips with 5% false alarms. It does NOT detect reasoning mistakes.

Runs in one background thread (the board can't run two LLM jobs at once). Only the standard library.
"""
import json
import queue
import re
import threading
import traceback
import urllib.request

SYSTEM = ("You solve multiple-choice math competition problems. Write a SHORT solution: at most 4 short lines "
          "with the key reasoning and calculations. Then write a last line 'Answer: X' where X is the letter.")
DIGIT = re.compile(r"\s*\d")


class LlamaScorer:
    """Scores a text token by token with a llama-server (needs --jinja for /apply-template)."""

    def __init__(self, url, timeout=600):
        self.url, self.timeout = url.rstrip("/"), timeout

    def _post(self, path, body):
        req = urllib.request.Request(self.url + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def prompt(self, problem):
        opts = problem.get("options") or {}
        user = (problem.get("text") or "").strip()
        if opts:
            user += "\n" + "\n".join(f"{k}) {v}" for k, v in sorted(opts.items()))
        ans = problem["answer"]
        user += f"\n\nHint: the correct answer is {ans}" + (f") {opts[ans]}." if ans in opts else ".")
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        return self._post("/apply-template", {"messages": msgs,
                                              "chat_template_kwargs": {"enable_thinking": False}})["prompt"]

    def tokens(self, text):
        """[(id, char_start, char_end)] — pieces can be partial UTF-8 bytes, so offsets are computed in bytes."""
        raw = text.encode("utf-8")
        b2c = [0] * (len(raw) + 1)
        pos = 0
        for i, ch in enumerate(text):
            n = len(ch.encode("utf-8"))
            for k in range(n):
                b2c[pos + k] = i
            pos += n
        b2c[len(raw)] = len(text)
        out, b = [], 0
        for t in self._post("/tokenize", {"content": text, "with_pieces": True})["tokens"]:
            p = t["piece"]
            n = len(p.encode("utf-8")) if isinstance(p, str) else len(p)
            out.append((t["id"], b2c[b], b2c[min(b + n, len(raw))]))
            b += n
        return out

    def nll(self, prompt, ids):
        g = "root ::= " + " ".join(f"<[{i}]>" for i in ids)
        out = self._post("/completion", {"prompt": prompt, "grammar": g, "n_probs": 1, "max_tokens": len(ids),
                                         "temperature": 0, "cache_prompt": True})
        cp = out.get("completion_probabilities") or []
        if len(cp) != len(ids):
            raise RuntimeError(f"scored {len(cp)} of {len(ids)} tokens")
        return [-c["logprob"] for c in cp]


def check(scorer, problem, text, threshold):
    """-> {"numbers": [{"start", "end", "text", "nll", "flag"}], "flagged": n, "max_nll": x}"""
    toks = scorer.tokens(text)
    nll = []
    for k in range(0, len(toks), 400):         # long texts in chunks (the prefix goes into the prompt)
        chunk = toks[k:k + 400]
        prefix = text[:chunk[0][1]]
        nll += scorer.nll(scorer.prompt(problem) + prefix, [t[0] for t in chunk])
    # group digit tokens into numbers; Qwen writes one digit per token. "2.5" / "2,5" stay one number.
    numbers, cur, sep = [], None, False
    for (tid, a, b), v in zip(toks, nll):
        piece = text[a:b]
        if DIGIT.fullmatch(piece):
            start = a + (len(piece) - len(piece.lstrip()))
            if cur and start == cur["end"] + (1 if sep else 0):
                cur["end"], cur["nll"] = b, max(cur["nll"], v)
            else:
                cur = {"start": start, "end": b, "nll": v}
                numbers.append(cur)
            sep = False
        elif cur and not sep and piece in (".", ",") and a == cur["end"]:
            sep = True                             # maybe a decimal point; decided by the next token
        else:
            cur, sep = None, False
    for n in numbers:
        n["text"] = text[n["start"]:n["end"]]
        n["nll"] = round(n["nll"], 2)
        n["flag"] = n["nll"] > threshold
    return {"numbers": numbers, "flagged": sum(n["flag"] for n in numbers),
            "max_nll": max((n["nll"] for n in numbers), default=0.0), "threshold": threshold}


class Worker:
    """One background thread; jobs are explanation ids, results are written back through the callbacks."""

    def __init__(self, cfg, load_job, save_result):
        c = cfg.get("checker") or {}
        self.enabled = bool(c) and c.get("kind", "llama") != "none"
        self.threshold = float(c.get("threshold", 5.0))
        self.scorer = LlamaScorer(c.get("url", "http://127.0.0.1:8081")) if self.enabled else None
        self.load_job, self.save_result = load_job, save_result
        self.q = queue.Queue()
        if self.enabled:
            threading.Thread(target=self._run, name="calc-checker", daemon=True).start()

    def submit(self, job_id):
        if self.enabled:
            self.q.put(job_id)

    def _run(self):
        while True:
            jid = self.q.get()
            try:
                problem, text = self.load_job(jid)
                self.save_result(jid, "done", check(self.scorer, problem, text, self.threshold))
            except Exception as e:
                traceback.print_exc()
                self.save_result(jid, "error", {"error": "No se pudo analizar ahora (¿está encendido el modelo?)",
                                                "detail": str(e)[:200]})
