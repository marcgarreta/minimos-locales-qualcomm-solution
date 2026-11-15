"""Text -> vector. Swap the model by changing config.json "embedder".

- "hash":  placeholder, no model. Hashed words, word pairs and character trigrams in 384 dims.
           Captures shared vocabulary only; good enough to test the pipeline.
- "llama": llama.cpp embedding server already on the board (bge-small, port 8082).

Every embedder returns an L2-normalised list of floats of length `dim`.
"""
import json
import math
import re
import urllib.request
import zlib

_WORD = re.compile(r"[a-záéíóúñüç]+|\d+", re.I)


def _normalise(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class HashEmbedder:
    name = "hash"

    def __init__(self, dim=384):
        self.dim = dim

    def _add(self, v, feat, w):
        h = zlib.crc32(feat.encode("utf-8"))
        v[h % self.dim] += w if (h >> 16) & 1 else -w

    def embed(self, text):
        v = [0.0] * self.dim
        words = [w.lower() for w in _WORD.findall(text or "")]
        for w in words:
            self._add(v, "w:" + w, 1.0)
            if len(w) > 3:
                for i in range(len(w) - 2):
                    self._add(v, "c:" + w[i:i + 3], 0.3)
        for a, b in zip(words, words[1:]):
            self._add(v, f"b:{a} {b}", 0.7)
        return _normalise(v)


class LlamaEmbedder:
    """llama.cpp `llama-server --embedding` (see config.env EMBED_PORT)."""
    name = "llama"

    def __init__(self, url, dim=384, timeout=20):
        self.url, self.dim, self.timeout = url, dim, timeout

    def embed(self, text):
        body = json.dumps({"content": text[:2000]}).encode()
        req = urllib.request.Request(self.url, body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.loads(r.read())
        if isinstance(out, list):
            out = out[0]
        vec = out["embedding"]
        if vec and isinstance(vec[0], list):   # newer llama.cpp returns one vector per token group
            vec = vec[0]
        return _normalise([float(x) for x in vec])


def make(cfg):
    e = cfg["embedder"]
    if e["kind"] == "llama":
        return LlamaEmbedder(e["url"], e.get("dim", 384))
    return HashEmbedder(e.get("dim", 384))
