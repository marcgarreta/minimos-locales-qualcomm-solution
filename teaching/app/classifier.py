"""Basic automatic classifier for new problems. Easy to remove or replace.

KnnClassifier: embed the text, take the k most similar problems in the bank, and vote
(weighted by similarity) for topic, then subtopic within that topic. The level suggestion
is the weighted median level of the neighbours.

To remove it: set "classifier": "none" in config.json; the teacher then picks everything.
To replace it: write a class with `classify(text) -> dict` (same keys) and return it in make().
"""


class NoClassifier:
    name = "none"

    def classify(self, text, topic=None):
        return {"topic": topic, "subtopic": None, "level": None, "confidence": 0.0, "neighbors": []}


class KnnClassifier:
    name = "knn"

    def __init__(self, embed, index, meta, k=15):
        self.embed, self.index, self.meta, self.k = embed, index, meta, k

    def classify(self, text, topic=None):
        """`topic` (optional) fixes the topic chosen by the teacher; then only the subtopic is voted."""
        if not text.strip() or not len(self.index):
            return NoClassifier().classify(text, topic)
        q = self.embed(text)
        nb = self.index.search(q, k=self.k, topic=topic)
        nb = [(pid, max(s, 0.0) + 1e-6) for pid, s in nb]
        votes = {}
        for pid, s in nb:
            t = self.meta(pid)["topic"]
            votes[t] = votes.get(t, 0) + s
        best = topic or max(votes, key=votes.get)
        total = sum(votes.values()) or 1
        sub = {}
        for pid, s in nb:
            m = self.meta(pid)
            if m["topic"] == best:
                sub[m["subtopic"]] = sub.get(m["subtopic"], 0) + s
        levels = sorted((self.meta(pid)["level"], s) for pid, s in nb)
        half, acc, level = sum(s for _, s in levels) / 2, 0, levels[0][0] if levels else 0
        for lv, s in levels:
            acc += s
            if acc >= half:
                level = lv
                break
        same = sorted((self.meta(pid)["num"], s) for pid, s in nb
                      if self.meta(pid)["level"] == level and self.meta(pid).get("num"))
        num, acc = None, 0
        for n, s in same:                       # weighted median question number at that level
            acc += s
            if acc >= sum(x for _, x in same) / 2:
                num = n
                break
        return {
            "topic": best, "num": num,
            "subtopic": max(sub, key=sub.get) if sub else None,
            "level": level,
            "confidence": round(votes.get(best, 0) / total, 2),
            "neighbors": [{"id": pid, "score": round(s, 3)} for pid, s in nb[:5]],
        }


def make(cfg, embed, index, meta):
    if cfg.get("classifier") == "knn":
        return KnnClassifier(embed, index, meta)
    return NoClassifier()
