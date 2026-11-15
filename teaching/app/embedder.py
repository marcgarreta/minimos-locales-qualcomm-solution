"""Text -> vector. Swap the model by changing config.json "embedder".

- "qwen":  Qwen3-Embedding-0.6B (Q8_0 GGUF, no instruction prompt, last-token pooling, 1024 dims)
           through llama-server's OpenAI endpoint. The bank's vectors are precomputed
           (seed/emb_qwen3.*), so the server is only needed for NEW texts; when it doesn't
           answer, service.Service approximates them (see Service.embed_text).
           Start it with:  llama-server -m Qwen3-Embedding-0.6B-Q8_0.gguf --embedding --pooling last --port 8082
- "llama": any other llama.cpp embedding server (e.g. bge-small on the board, 384 dims).
- "hash":  no model. Hashed words, word pairs and character trigrams in 384 dims; only shared
           vocabulary. Also used internally to approximate Qwen vectors when its server is down.

Every embedder returns an L2-normalised vector of length `dim`, or raises EmbedderUnavailable.
"""
import json
import math
import re
import urllib.request
import zlib

_WORD = re.compile(r"[a-záéíóúñüç]+|\d+", re.I)


class EmbedderUnavailable(Exception):
    pass


def _normalise(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class HashEmbedder:
    name = "hash"
    live = True

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
    """llama.cpp `llama-server --embedding`, OpenAI-style /v1/embeddings or native /embedding."""
    live = False

    def __init__(self, url, dim, name="llama", timeout=30):
        self.url, self.dim, self.name, self.timeout = url, dim, name, timeout

    def embed(self, text):
        openai = self.url.rstrip("/").endswith("/v1/embeddings")
        body = {"input": text[:4000]} if openai else {"content": text[:4000]}
        req = urllib.request.Request(self.url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.loads(r.read())
        except (OSError, ValueError) as e:
            raise EmbedderUnavailable(f"{self.name}: {e}") from e
        if openai:
            vec = out["data"][0]["embedding"]
        else:
            out = out[0] if isinstance(out, list) else out
            vec = out["embedding"]
            if vec and isinstance(vec[0], list):
                vec = vec[-1]
        if len(vec) != self.dim:          # e.g. another model is serving on that port
            raise EmbedderUnavailable(f"{self.name}: got {len(vec)} dims, expected {self.dim}")
        return _normalise([float(x) for x in vec])

    def check(self):
        """True if the server answers now (short timeout)."""
        try:
            old, self.timeout = self.timeout, 3
            self.embed("ping")
            return True
        except EmbedderUnavailable:
            return False
        finally:
            self.timeout = old


def make(cfg):
    e = cfg["embedder"]
    if e["kind"] == "qwen":
        return LlamaEmbedder(e.get("url", "http://127.0.0.1:8082/v1/embeddings"), e.get("dim", 1024),
                             name=e.get("model", "qwen3-embedding-0.6b"))
    if e["kind"] == "llama":
        return LlamaEmbedder(e["url"], e.get("dim", 384), name=e.get("model", "llama"))
    return HashEmbedder(e.get("dim", 384))
