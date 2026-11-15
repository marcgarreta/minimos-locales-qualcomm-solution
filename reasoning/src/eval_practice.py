"""Run the REAL submission pipeline (repo_official/copilot/pipeline.solve) on labelled rows and report.

  .venv/bin/python src/eval_practice.py --input data/bilingual/practice/records.jsonl --name base
Servers must be running (scripts/start_servers_laptop.sh [TEXT_GGUF]).
Projected board seconds: text = prompt/LLM_READ_TPS + generated/LLM_WRITE_TPS (config.env; includes the fallback
letter call); vision = prompt/11 + 1/5.9 (Qwen3.5-0.8B README speeds; image tokens counted in prompt).
Projections, not board measurements. Figure rows use the vision server on 8083 if it is up, else the text route:
report figure/text separately when comparing (the reference 40/100 includes 5 vision-route answers).
"""
import argparse, csv, json, sys, time
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "repo_official"))
from copilot.pipeline import solve   # noqa: E402
from copilot.config import CONFIG    # noqa: E402

# board speeds (tokens/s) used for the projection: text model from config.env (set them for YOUR student, measured
# with board/07_measure_speed.py), vision model = Qwen3.5-0.8B README measurements.
TEXT_READ, TEXT_WRITE = float(CONFIG.get("LLM_READ_TPS", 5.6)), float(CONFIG.get("LLM_WRITE_TPS", 4.5))
VISION_READ, VISION_WRITE = 11.0, 5.9

ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True); ap.add_argument("--name", required=True)
ap.add_argument("--limit", type=int, default=0)
a = ap.parse_args()
rows = [json.loads(l) for l in open(a.input)]
if a.limit:
    rows = rows[:a.limit]
root = str(Path(a.input).resolve().parent)
out = ROOT / "results" / f"practice-{a.name}.jsonl"
out.parent.mkdir(exist_ok=True)
res = []
with open(out, "w") as f:
    for p in rows:
        r = solve(p, image_root=root)
        vision = r["status"].startswith("vision")
        board = (r["prompt_tokens"] / VISION_READ + 1 / VISION_WRITE) if vision else \
            (r["prompt_tokens"] / TEXT_READ + r.get("generated_tokens", 0) / TEXT_WRITE)
        rec = {"id": p["id"], "language": p["language"], "text_only": p["text_only"], "level": p["level"],
               "label": p["label"], "answer": r["answer"], "correct": r["answer"] == p["label"], "status": r["status"],
               "laptop_s": r["seconds"], "board_s_proj": round(board, 1), "prompt_tokens": r["prompt_tokens"],
               "generated_tokens": r.get("generated_tokens", 0), "images_sent": r.get("images_sent", 0)}
        res.append(rec); f.write(json.dumps(rec) + "\n"); f.flush()
        print(f"{p['id']} {p['language']} {'txt' if p['text_only'] else 'fig'} -> {r['answer']} ({p['label']}) "
              f"{r['status']} board~{board:.0f}s", flush=True)
def show(title, key):
    g = defaultdict(list)
    for r in res: g[key(r)].append(r)
    print(title, {k: f"{sum(x['correct'] for x in v)}/{len(v)}" for k, v in sorted(g.items())})
n = len(res); ok = sum(r["correct"] for r in res)
ok60 = sum(r["correct"] and r["board_s_proj"] <= 60 for r in res)
print(f"\n== {a.name}: correct {ok}/{n} = {ok/n:.3f} | correct AND projected <=60 s: {ok60}/{n} = {ok60/n:.3f}")
show("by language:", lambda r: r["language"])
show("text/figure:", lambda r: "text" if r["text_only"] else "figure")
show("by level:", lambda r: r["level"])
st = defaultdict(int)
for r in res: st[r["status"].split(":")[0]] += 1
print("statuses:", dict(st))
print("projected board s: mean %.1f max %.1f, over 60: %d" % (sum(r['board_s_proj'] for r in res)/n,
      max(r['board_s_proj'] for r in res), sum(r['board_s_proj'] > 60 for r in res)))
print("answer letters:", dict(sorted(defaultdict(int, {k: sum(r['answer']==k for r in res) for k in 'ABCDE'}).items())))
