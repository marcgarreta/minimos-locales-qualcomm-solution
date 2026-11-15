"""Precompute the 3D map of each topic (runs on the laptop; needs numpy, pandas, umap-learn).

    .venv/Scripts/python arduino/seed/build_layout.py

For every topic, ONE UMAP is fitted on all its problems (every level together), so the
2D position of a problem means the same thing on every level plane and the planes can be
stacked without distortion. The vertical axis is the general difficulty (app/difficulty.py:
level + question number). Each problem is linked to its K most similar problems (cosine) a
few places up the ladder, which is the same level except for its last questions: the arrows
of the "tree".

Inputs:  seed/problems.jsonl (ids, topic, level), data/texts.parquet (row order of the
         embeddings), results/emb/qwen3doc-0.6b-q8.npy (Qwen3-Embedding-0.6B Q8_0, no prompt: the app's model).
Output:  seed/layout.json  {"model", "topics": {topic: {"pos": {id: [x, y]}, "edges": [[a, b, cos]]}}}
Positions are centred and scaled to about [-1, 1].
"""
import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BASES = [HERE.parent, REPO, REPO.parent]


def find(rel):
    for base in BASES:
        if (base / rel).exists():
            return base / rel
    return REPO / rel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--problems", default=str(HERE / "problems.jsonl"))
    ap.add_argument("--texts", default=str(find("data/texts.parquet")))
    ap.add_argument("--emb", default=str(find("results/emb/qwen3doc-0.6b-q8.npy")))
    ap.add_argument("--k", type=int, default=2, help="arrows from each problem to harder similar ones")
    ap.add_argument("--step", type=int, default=4, help="how many places up the difficulty ladder to look first")
    ap.add_argument("--neighbors", type=int, default=15)
    ap.add_argument("--min-dist", type=float, default=0.25)
    a = ap.parse_args()

    import pandas as pd
    import umap
    warnings.filterwarnings("ignore")

    probs = [json.loads(line) for line in open(a.problems, encoding="utf-8")]
    texts = pd.read_parquet(a.texts)
    emb = np.load(a.emb)
    assert len(texts) == len(emb), "embeddings and texts.parquet must have the same rows"
    row = {r.id: i for i, r in enumerate(texts.itertuples()) if r.language == "eng"}

    sys.path.insert(0, str(HERE.parent))
    from app.difficulty import general, ladder, neighbours, question_number
    lad = ladder((p["level"], question_number(p["id"])) for p in probs)

    out = {"model": Path(a.emb).stem, "topics": {}}
    for topic in sorted({p["topic"] for p in probs}):
        ps = [p for p in probs if p["topic"] == topic and p["id"] in row]
        X = emb[[row[p["id"]] for p in ps]].astype(np.float32)
        X /= np.linalg.norm(X, axis=1, keepdims=True)
        if len(ps) > a.neighbors + 2:
            P = umap.UMAP(n_neighbors=a.neighbors, min_dist=a.min_dist, metric="cosine",
                          random_state=42).fit_transform(X)
        else:                                   # tiny topics: a circle is enough
            ang = np.linspace(0, 2 * np.pi, len(ps), endpoint=False)
            P = np.c_[np.cos(ang), np.sin(ang)]
        P = P - np.median(P, axis=0)
        P /= max(np.percentile(np.abs(P), 98), 1e-6)
        P = np.clip(P, -1.25, 1.25)

        gs = [general(lad, p["level"], question_number(p["id"])) for p in ps]
        items = [(i, g, p["level"]) for i, (g, p) in enumerate(zip(gs, ps))]
        edges = []
        for i, p in enumerate(ps):
            nxt = neighbours(items, gs[i], p["level"], +1, a.step, need=a.k)      # a few places harder, same level first
            if not nxt:
                continue
            sims = X[nxt] @ X[i]
            for j in np.argsort(-sims)[:a.k]:
                edges.append([p["id"], ps[nxt[j]]["id"], round(float(sims[j]), 3)])
        out["topics"][topic] = {"pos": {p["id"]: [round(float(x), 4), round(float(y), 4)] for p, (x, y) in zip(ps, P)},
                                "edges": edges}
        print(f"{topic:28s} {len(ps):4d} problems  {len(edges):4d} arrows  difficulty {min(gs)}-{max(gs)}")
    (HERE / "layout.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("wrote", HERE / "layout.json")


if __name__ == "__main__":
    main()
