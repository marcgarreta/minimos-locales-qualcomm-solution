"""Write the bank's Qwen3-Embedding vectors next to problems.jsonl (runs on the laptop).

    .venv/Scripts/python arduino/seed/build_embeddings.py

The board can't run Qwen3-Embedding-0.6B for 1,747 problems at start-up, so the vectors come
precomputed: results/emb/qwen3doc-0.6b-q8.npy (Qwen3-Embedding-0.6B Q8_0, no instruction
prompt, last-token pooling; identical to llama-server --embedding --pooling last, cosine 1.0000).

Output: seed/emb_qwen3.f32 (float32, one row per id, L2-normalised) + seed/emb_qwen3.json
({"model", "dim", "ids"}). Both are git-ignored (derived from M3Kang).
"""
import argparse
import json
from array import array
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def find(rel):
    for base in (HERE.parent, REPO, REPO.parent):
        if (base / rel).exists():
            return base / rel
    return REPO / rel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emb", default=str(find("results/emb/qwen3doc-0.6b-q8.npy")))
    ap.add_argument("--texts", default=str(find("data/texts.parquet")))
    ap.add_argument("--model", default="qwen3-embedding-0.6b")
    ap.add_argument("--out", default="emb_qwen3")
    a = ap.parse_args()

    import pandas as pd
    texts = pd.read_parquet(a.texts)
    emb = np.load(a.emb).astype(np.float32)
    assert len(texts) == len(emb), "embeddings and texts.parquet must have the same rows"
    row = {r.id: i for i, r in enumerate(texts.itertuples()) if r.language == "eng"}
    ids = [json.loads(line)["id"] for line in open(HERE / "problems.jsonl", encoding="utf-8")]
    ids = [i for i in ids if i in row]
    X = emb[[row[i] for i in ids]]
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    with open(HERE / f"{a.out}.f32", "wb") as f:
        array("f", X.ravel().tolist()).tofile(f)
    (HERE / f"{a.out}.json").write_text(json.dumps({"model": a.model, "dim": int(X.shape[1]), "ids": ids}), encoding="utf-8")
    print(f"wrote {len(ids)} x {X.shape[1]} vectors ({a.model}) to {HERE / (a.out + '.f32')}")


if __name__ == "__main__":
    main()
