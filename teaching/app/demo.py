"""Example classroom created on the first start ("demo_students": true in config.json).

Five students with fixed, easy codes and a few simulated weeks of answers, so every
screen has data from the first minute. Each has a hidden "true" level per topic and
answers right with the probability the progress model expects.
Turn it off with "demo_students": false (only acts when there are no students yet).
"""
import math
import random

STUDENTS = [
    ("LUC-123", "Lucía Martín", 4),
    ("HUG-123", "Hugo García", 3),
    ("MAR-123", "Martina López", 3),
    ("PAB-123", "Pablo Sánchez", 2),
    ("SOF-123", "Sofía Navarro", 4),
]
CLASSROOM = "4º A"


def _move_back(svc, aid, days):
    """Date a simulated mission in a past week, so "today" counters and streaks stay real."""
    shift = f"-{days} days"
    with svc.db:
        iso = "strftime('%Y-%m-%dT%H:%M:%S', {}, ?)"
        svc.db.execute(f"UPDATE assignments SET created_at={iso.format('created_at')}, submitted_at={iso.format('submitted_at')},"
                       " due=date(due, ?) WHERE id=?", (shift, shift, shift, aid))
        svc.db.execute(f"UPDATE attempts SET created_at={iso.format('created_at')} WHERE assignment_id=?", (shift, aid))


def create(svc, rounds=3, seed=7):
    rng = random.Random(seed)
    old_rng, svc.rng = svc.rng, rng
    svc.first.rng = random.Random(seed)
    try:
        for code, name, start in STUDENTS:
            svc.add_student({"name": name, "classroom": CLASSROOM, "start_level": start}, code=code)
            true = {t: min(7.9, max(0.2, start + 0.5 + rng.gauss(0, 1.1))) for t in svc.topics}
            for k in range(rounds):
                a = svc.student_home(code)["current"]
                answers = {}
                for it in a["items"]:
                    truth = svc.problem(it["id"])["answer"]
                    p = 1 / (1 + math.exp(-1.6 * (true[it["topic"]] - it["level"] - 0.5)))
                    wrong = [x for x in "ABCDE" if x != truth]
                    answers[it["id"]] = truth if rng.random() < max(p, 0.2) else rng.choice(wrong)
                svc.submit(code, {"assignment_id": a["id"], "answers": answers})
                _move_back(svc, a["id"], days=7 * (rounds - k))
    finally:
        svc.rng = old_rng
    print(f"created {len(STUDENTS)} example students: " + ", ".join(c for c, _, _ in STUDENTS), flush=True)
