"""Which problems a student gets.

- RandomRecommender: first task of a new student (no data yet). Random problems near the
  starting level, spread over the topics. Replace it later with a smarter cold start.
- prerequisites(): for a problem the student got wrong, the most similar problems
  (embedding cosine) of a LOWER level, same topic first. "Do these before this one."
- weekend_task(): next task = prerequisites of the mistakes + practice at the current
  level in the weakest topics + one challenge one level up in the strongest topic.

All functions receive a `bank` (see service.Service) so they never touch SQL directly.
"""
import random


class RandomRecommender:
    name = "random"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def initial(self, bank, start_level, n, topics):
        lo, hi = max(0, start_level - 1), start_level + 1
        picked, topics = [], list(topics)
        self.rng.shuffle(topics)
        for i in range(n * 4):
            if len(picked) >= n:
                break
            t = topics[i % len(topics)]
            pool = [p for p in bank.ids_where(topic=t, level_min=lo, level_max=hi) if p not in picked]
            if pool:
                picked.append(self.rng.choice(pool))
        return [{"problem_id": p, "role": "practica"} for p in picked]


def prerequisites(bank, problem_id, k, exclude, step=4):
    """Similar problems a little easier than `problem_id`: a few places lower on the general
    difficulty ladder of the same topic (same level; the level below only when it is one of
    the first questions). For the very first questions: similar ones of the same difficulty band."""
    from .difficulty import neighbours
    p = bank.get(problem_id)
    vec = bank.index.vector(problem_id)
    if vec is None:
        return []
    exclude = set(exclude) | {problem_id}
    items = [(q, bank.get(q)["g"], bank.get(q)["level"]) for q in bank.ids_where(topic=p["topic"]) if q not in exclude]
    cand = neighbours(items, p["g"], p["level"], -1, step, need=k)
    if not cand:                            # the very first questions: similar ones of about the same difficulty
        cand = neighbours(items, p["g"] - 1, p["level"], +1, step, need=k)
    same = [c for c in cand if bank.get(c)["level"] == p["level"]]
    ranked = bank.index.rank(vec, same) + bank.index.rank(vec, [c for c in cand if c not in same])
    return [h for h, _ in ranked[:k]]


def weekend_task(bank, skills, mistakes, solved, n, per_mistake, rng=random):
    """skills: {topic: theta}; mistakes: problem ids failed; solved: ids answered correctly."""
    items, used = [], set(solved)

    def add(pid, role, because=None):
        if pid and pid not in used and len(items) < n:
            used.add(pid)
            items.append({"problem_id": pid, "role": role, "because": because})

    for m in mistakes:
        for pre in prerequisites(bank, m, per_mistake, used):
            add(pre, "refuerzo", m)
    room = n - len(items)
    order = sorted(skills, key=skills.get)              # weakest first
    practice_topics = order[:2] + order[2:3]
    for t in practice_topics:
        if room <= 1:
            break
        lv = int(skills[t])
        pool = [p for p in bank.ids_where(topic=t, level_min=lv, level_max=lv) if p not in used]
        if pool:
            add(rng.choice(pool), "practica")
            room -= 1
    strongest = order[-1] if order else None
    if strongest:
        lv = min(int(skills[strongest]) + 1, 7)
        pool = [p for p in bank.ids_where(topic=strongest, level_min=lv, level_max=lv) if p not in used]
        if pool:
            add(rng.choice(pool), "reto")
    while len(items) < n:                                # fill up at the current levels
        t = rng.choice(order)
        lv = int(skills[t])
        pool = [p for p in bank.ids_where(topic=t, level_min=lv, level_max=lv) if p not in used]
        if not pool:
            break
        add(rng.choice(pool), "practica")
    return items
