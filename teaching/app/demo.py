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

# A sixth student for the live demo of the calculation check: no history and always the same
# mission, so the demo can be repeated after `python3 server.py --reset-demo` (see README, "Demo").
# Problem 1 (lvl-0_2016_16): a 15 x 9 cm rectangle loses a 2 cm square at each corner; the
# perimeter stays 2 x (15 + 9) = 48 cm. Answer B (40 cm) and explain
# "Recortar las esquinas no cambia el perímetro. 15 + 9 = 20 y 2 x 20 = 40 cm." -> 20 is marked red.
DEMO_STUDENT = ("DEM-123", "Elena Ruiz", 1)
DEMO_MISSION = ["lvl-0_2016_16", "lvl-0_2015_10", "lvl-1_2024_2", "lvl-0_2019_15", "lvl-0_2015_1"]


def create_demo_student(svc, mission=None):
    """The demo student and her fixed mission; skipped if any problem is missing from the bank."""
    ids = mission or DEMO_MISSION
    if any(pid not in svc._meta for pid in ids):
        return None
    code, name, start = DEMO_STUDENT
    svc.add_student({"name": name, "classroom": CLASSROOM, "start_level": start}, code=code)
    a = svc.student_home(code)["current"]
    with svc.lock, svc.db:
        svc.db.execute("DELETE FROM assignment_items WHERE assignment_id=?", (a["id"],))
        svc.db.executemany(
            "INSERT INTO assignment_items (assignment_id, position, problem_id, role) VALUES (?,?,?,?)",
            [(a["id"], i, pid, "practica") for i, pid in enumerate(ids)])
        svc.db.execute("UPDATE assignments SET title=? WHERE id=?", ("Misión de demostración", a["id"]))
    return code


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
    codes = [c for c, _, _ in STUDENTS]
    if create_demo_student(svc):
        codes.append(DEMO_STUDENT[0])
    print(f"created {len(codes)} example students: " + ", ".join(codes), flush=True)
