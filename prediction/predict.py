#!/usr/bin/env python3
"""Official entry point: answer every problem with one letter, A to E (same interface as the README).

    python3 predict.py --input problems.jsonl --output predictions.csv

Solver: Qwen3.5 2B Q4_0 + permutation ensemble (copilot/perm.py), text only (figure images are never sent).
Needs board/start_server.sh running (2B on 127.0.0.1:8081, A53 build). Every problem gets a valid letter
in under 60 s: the number of option orders is planned from the token count, and any error or timeout
answers FALLBACK_ANSWER (D).

Input: one JSON object per line with at least "id" and "text", plus "options" ({"A": ..., "E": ...}) and
"language" when available. Output: a CSV with id, language, answer, seconds, status.
"""
import argparse
import csv
import json
import sys
import time

from copilot.config import CONFIG
from copilot.perm import solve

LETTERS = "ABCDE"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--rag", type=int, default=0, help="ignored (kept for the README's command line)")
    p.add_argument("--index", default="data/index.db", help="ignored")
    args = p.parse_args()

    with open(args.input, encoding="utf-8") as f:
        problems = [json.loads(line) for line in f if line.strip()]

    with open(args.output, "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["id", "language", "answer", "seconds", "status"])
        for n, problem in enumerate(problems, 1):
            start = time.perf_counter()
            try:
                result = solve(problem)
            except Exception as error:  # never leave a problem without a valid letter
                result = {"answer": CONFIG["FALLBACK_ANSWER"], "status": f"error: {error}"}
            if result.get("answer") not in LETTERS:
                result["answer"] = CONFIG["FALLBACK_ANSWER"]
            seconds = round(time.perf_counter() - start, 2)
            writer.writerow([problem["id"], problem.get("language", ""), result["answer"], seconds, result["status"]])
            out.flush()
            print(f"[{n}/{len(problems)}] {problem['id']} -> {result['answer']} in {seconds:.1f} s "
                  f"({result['status']}, {result.get('orders', 0)} orders)", file=sys.stderr)


if __name__ == "__main__":
    main()
