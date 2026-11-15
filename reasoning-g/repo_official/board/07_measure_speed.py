#!/usr/bin/env python3
"""Measure the text model's real reading/writing speed ON THE BOARD and print the config.env values.

    python3 board/07_measure_speed.py            # text server on LLM_PORT (8081)

The solver sizes each problem's reasoning budget from LLM_READ_TPS / LLM_WRITE_TPS. Wrong values never break the
60 s limit (every request has an HTTP timeout = time left, and llama-server cancels abandoned requests), but too-high
values cause more deadline fallbacks and too-low values waste reasoning time. Re-run after changing the model.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from copilot.config import CONFIG  # noqa: E402

URL = f"http://127.0.0.1:{CONFIG['LLM_PORT']}/v1/chat/completions"
PROBLEM = ("Mother Kangaroo and her daughter weigh 60 kg together. The mother weighs 52 kg. A rectangle 15 cm by 9 cm "
           "has a square with perimeter 8 cm cut from each corner. What is the perimeter of the resulting figure? ") * 2


def post(body):
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=300))


post({"messages": [{"role": "user", "content": "hi"}], "max_tokens": 2})            # warm-up
reads, writes = [], []
for i in range(3):
    t = post({"messages": [{"role": "user", "content": f"{i}. {PROBLEM}"}], "max_tokens": 60, "temperature": 0,
              "ignore_eos": True, "cache_prompt": False})["timings"]
    reads.append(t["prompt_per_second"]); writes.append(t["predicted_per_second"])
    print(f"run {i}: read {t['prompt_n']} tokens at {t['prompt_per_second']:.2f}/s, "
          f"wrote {t['predicted_n']} at {t['predicted_per_second']:.2f}/s")
r, w = sorted(reads)[1], sorted(writes)[1]
print(f"\nSet in config.env (slightly conservative):\nLLM_READ_TPS={r * 0.9:.1f}\nLLM_WRITE_TPS={w * 0.9:.1f}")
print(f"currently configured: LLM_READ_TPS={CONFIG.get('LLM_READ_TPS')} LLM_WRITE_TPS={CONFIG.get('LLM_WRITE_TPS')}")
