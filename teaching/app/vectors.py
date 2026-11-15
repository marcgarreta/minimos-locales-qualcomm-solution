"""In-memory vector index over the problem embeddings stored in SQLite.

Vectors live in SQLite (problems.embedding, float32 BLOB) and are loaded once into a
contiguous matrix. A query is one matrix-vector product (numpy if present, pure Python
otherwise) with optional filters on level / topic / excluded ids. For a few thousand
problems this is ~1 ms with numpy and well under 100 ms without it.
"""
from array import array

try:
    import numpy as np
except ImportError:  # the board's Python image may not ship numpy
    np = None


def to_blob(vec):
    return array("f", vec).tobytes()


def from_blob(blob):
    a = array("f")
    a.frombytes(blob)
    return a


def _row(vec):
    return vec if isinstance(vec, array) and vec.typecode == "f" else array("f", vec)


class VectorIndex:
    def __init__(self, dim):
        self.dim = dim
        self.ids, self.levels, self.topics = [], [], []
        self._rows = []        # pure-python rows
        self._mat = None       # numpy matrix, rebuilt lazily
        self._pos = {}

    def __len__(self):
        return len(self.ids)

    def add(self, pid, vec, level, topic):
        if pid in self._pos:
            i = self._pos[pid]
            self._rows[i], self.levels[i], self.topics[i] = _row(vec), level, topic
        else:
            self._pos[pid] = len(self.ids)
            self.ids.append(pid)
            self.levels.append(level)
            self.topics.append(topic)
            self._rows.append(_row(vec))
        self._mat = None

    def vector(self, pid):
        i = self._pos.get(pid)
        return None if i is None else self._rows[i]

    def rank(self, q, ids):
        """(id, cosine) for the given ids, most similar first."""
        out = []
        for pid in ids:
            v = self.vector(pid)
            if v is not None:
                out.append((pid, sum(a * b for a, b in zip(v, q))))
        out.sort(key=lambda t: -t[1])
        return out

    def _scores(self, q):
        if np is not None:
            if self._mat is None:
                self._mat = np.frombuffer(b"".join(r.tobytes() for r in self._rows), dtype=np.float32).reshape(-1, self.dim)
                self._lv = np.asarray(self.levels)
                self._tp = np.asarray(self.topics, dtype=object)
            return self._mat @ np.asarray(q, dtype=np.float32)
        return [sum(a * b for a, b in zip(r, q)) for r in self._rows]

    def search(self, q, k=10, level_lt=None, level_le=None, level_eq=None, topic=None, exclude=()):
        """Top-k (id, cosine) pairs. Vectors are normalised, so dot product = cosine."""
        if not self.ids:
            return []
        s = self._scores(q)
        exclude = set(exclude)
        if np is not None:
            mask = np.ones(len(self.ids), dtype=bool)
            if level_lt is not None:
                mask &= self._lv < level_lt
            if level_le is not None:
                mask &= self._lv <= level_le
            if level_eq is not None:
                mask &= self._lv == level_eq
            if topic is not None:
                mask &= self._tp == topic
            s = np.where(mask, s, -np.inf)
            order = np.argsort(-s)
            out = []
            for i in order:
                if s[i] == -np.inf or len(out) >= k:
                    break
                if self.ids[i] not in exclude:
                    out.append((self.ids[i], float(s[i])))
            return out
        cand = []
        for i, sc in enumerate(s):
            lv = self.levels[i]
            if ((level_lt is not None and lv >= level_lt) or (level_le is not None and lv > level_le)
                    or (level_eq is not None and lv != level_eq)
                    or (topic is not None and self.topics[i] != topic) or self.ids[i] in exclude):
                continue
            cand.append((self.ids[i], sc))
        cand.sort(key=lambda t: -t[1])
        return cand[:k]
