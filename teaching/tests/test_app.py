"""End-to-end tests of the service and the HTTP API, on a tiny fake bank (no M3Kang data).

    python -m unittest discover -s tests -v       (from arduino/)
"""
import json
import random
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import progress, recommender  # noqa: E402
from app.service import ApiError, Service, next_weekend  # noqa: E402
from app.vectors import VectorIndex  # noqa: E402
from app.web import make_handler  # noqa: E402

TOPICS = {
    "Algebra": ("Equations and unknowns", "solve the equation x plus unknown value equals number"),
    "Plane geometry": ("Area and perimeter", "area of the square rectangle perimeter side length cm"),
    "Arithmetic": ("Operations and calculation", "compute the sum product of numbers operation result"),
}


def fake_seed(folder):
    cats, lines, i = [], [], 0
    for topic, (subtopic, words) in TOPICS.items():
        for level in range(8):
            for k in range(3):
                i += 1
                pid = f"lvl-{level}_20{10 + k}_{5 + 10 * k}-{topic[:3]}_{5 + 10 * k}"
                cats.append({"id": pid, "level": level, "topic": topic, "subtopic": subtopic})
                lines.append(json.dumps({"id": pid, "topic": topic, "subtopic": subtopic, "level": level,
                                         "text": f"{words} variant {k} level {level}", "answer": "ABCDE"[i % 5],
                                         "options": {L: str(n) for n, L in enumerate("ABCDE")}, "image": None}))
    cats.append({"id": "x", "level": 0, "topic": "Other", "subtopic": "Unclear"})
    (folder / "categories_eng.json").write_text(json.dumps(cats))
    (folder / "problems.jsonl").write_text("\n".join(lines))


def make_service(tmp):
    seed = Path(tmp) / "seed"
    seed.mkdir()
    fake_seed(seed)
    cfg = {"school_name": "Test", "teacher": {"user": "profe", "password": "pw", "name": "Profe"},
           "portal_ip": "192.168.4.1", "port": 0, "dev": True, "data_dir": str(Path(tmp) / "data"),
           "seed_dir": str(seed), "embedder": {"kind": "hash", "dim": 64}, "classifier": "knn",
           "answer_zone_path": str(Path(tmp) / "nope"), "initial_problems": 6, "weekend_problems": 8,
           "max_prerequisites_per_mistake": 2, "levels": 8}
    return Service(cfg, rng=random.Random(1))


class ProgressTest(unittest.TestCase):
    def test_lucky_hard_answer_does_not_jump_levels(self):
        theta, n = progress.update(progress.initial_theta(1), 0, level=7, correct=True)
        self.assertLess(theta, 2.5)

    def test_mistakes_on_easy_problems_lower_level(self):
        theta, n = 3.5, 5
        for _ in range(4):
            theta, n = progress.update(theta, n, level=2, correct=False)
        self.assertLess(theta, 3.0)

    def test_next_weekend_is_a_sunday_in_the_future(self):
        import datetime as dt
        for d in range(7):
            day = dt.date(2026, 11, 9) + dt.timedelta(days=d)
            due = dt.date.fromisoformat(next_weekend(day))
            self.assertEqual(due.weekday(), 6)
            self.assertGreaterEqual((due - day).days, 2)


class VectorTest(unittest.TestCase):
    def test_filters_and_order(self):
        idx = VectorIndex(2)
        idx.add("a", [1, 0], 3, "T")
        idx.add("b", [0.8, 0.6], 1, "T")
        idx.add("c", [0, 1], 0, "U")
        self.assertEqual([i for i, _ in idx.search([1, 0], k=3)], ["a", "b", "c"])
        self.assertEqual([i for i, _ in idx.search([1, 0], k=3, level_lt=3)], ["b", "c"])
        self.assertEqual([i for i, _ in idx.search([1, 0], k=3, topic="U")], ["c"])
        self.assertEqual([i for i, _ in idx.search([1, 0], k=3, exclude={"a"})], ["b", "c"])


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.svc = make_service(self.tmp.name)

    def tearDown(self):
        self.svc.db.close()
        self.tmp.cleanup()

    def test_seed_and_taxonomy(self):
        self.assertEqual(len(self.svc.index), 72)
        self.assertNotIn("Other", self.svc.topics)

    def test_classifier_finds_topic(self):
        r = self.svc.classify({"text": "What is the area of a square with perimeter 20 cm?"})
        self.assertEqual(r["topic"], "Plane geometry")

    def test_general_difficulty_ladder(self):
        from app import difficulty as d
        self.assertEqual(d.question_number("lvl-1_2019_3"), 3)
        self.assertIsNone(d.question_number("profe-0001"))
        lad = d.ladder([(0, 24), (1, 24), (2, 30)], levels=3)
        self.assertEqual(d.general(lad, 0, 8), 8)
        self.assertEqual(d.general(lad, 1, 3), 27)            # after the 24 questions of level 0
        self.assertEqual(d.general(lad, 2, 1), 49)
        items = [("a", 10), ("b", 12), ("c", 30)]
        self.assertEqual(d.window(items, 9, +1), ["a", "b"])  # a few places harder
        self.assertEqual(d.window(items, 12, +1), ["c"])      # widens when nothing is close

    def test_prerequisites_are_a_little_easier_and_same_level(self):
        pid = next(p for p, m in self.svc._meta.items()
                   if m["topic"] == "Algebra" and m["level"] == 5 and m["num"] == 25)
        pre = recommender.prerequisites(self.svc, pid, 2, set())
        self.assertEqual(len(pre), 2)
        for p in pre:
            self.assertLess(self.svc.get(p)["g"], self.svc.get(pid)["g"])
            self.assertEqual(self.svc.get(p)["level"], 5)      # same level: questions 5 and 15
            self.assertEqual(self.svc.get(p)["topic"], "Algebra")
        first = next(p for p, m in self.svc._meta.items()
                     if m["topic"] == "Algebra" and m["level"] == 5 and m["num"] == 5)
        down = recommender.prerequisites(self.svc, first, 1, set())
        self.assertEqual(self.svc.get(down[0])["level"], 4)    # first question: reaches the level below

    def test_student_full_cycle(self):
        s = self.svc.add_student({"name": "Ana Pérez", "classroom": "4A", "start_level": 2})
        home = self.svc.student_home(s["id"])
        items = home["current"]["items"]
        self.assertEqual(len(items), 6)
        self.assertNotIn("answer", items[0])                      # students never see answers before submitting
        truth = {p: self.svc.problem(p)["answer"] for p in (i["id"] for i in items)}
        answers = {p: a for p, a in truth.items()}
        wrong = items[0]["id"]
        answers[wrong] = "B" if truth[wrong] != "B" else "C"
        r = self.svc.submit(s["id"], {"assignment_id": home["current"]["id"], "answers": answers})
        self.assertEqual(r["result"]["correct"], 5)
        self.assertIn(wrong, r["result"]["prerequisites"])
        nxt = self.svc.student_home(s["id"])["current"]
        self.assertEqual(nxt["kind"], "finde")
        roles = [i["role"] for i in nxt["items"]]
        if self.svc.get(wrong)["level"] > 0:
            self.assertIn("refuerzo", roles)
        with self.assertRaises(ApiError):
            self.svc.submit(s["id"], {"assignment_id": home["current"]["id"], "answers": answers})

    def test_example_students_on_first_start(self):
        self.svc.cfg["demo_students"] = True
        svc2 = Service(self.svc.cfg)            # same data dir, no students yet -> creates them
        codes = [s["id"] for s in svc2.list_students()]
        self.assertIn("LUC-123", codes)
        self.assertEqual(len(codes), 5)
        self.assertGreater(svc2.student_detail("LUC-123")["answered"], 0)
        svc3 = Service(self.svc.cfg)            # second start: nothing new
        self.assertEqual(len(svc3.list_students()), 5)
        svc2.db.close()
        svc3.db.close()

    def test_board_status_counts_without_personal_data(self):
        s = self.svc.add_student({"name": "Ana Pérez", "classroom": "4A", "start_level": 1})
        self.svc.login({"role": "student", "code": s["id"]})
        a = self.svc.student_home(s["id"])["current"]
        self.svc.submit(s["id"], {"assignment_id": a["id"], "answers": {p["id"]: "A" for p in a["items"]}})
        from app.service import board_status
        b = board_status(self.svc)
        self.assertEqual((b["students"], b["online_students"], b["submissions_today"]), (1, 1, 1))
        self.assertEqual(b["events"][-1]["kind"], "submit")
        self.assertEqual(len(b["topic_avg"]), len(self.svc.topics))
        self.assertNotIn("Ana", json.dumps(b))
        self.assertNotIn(s["id"], json.dumps(b))

    def test_clock_is_fixed_only_when_unset(self):
        import datetime as dt
        from unittest import mock
        from app import service
        ms = 1794680000000                       # 2026-11-14
        self.assertFalse(service.sync_clock(ms))   # laptop clock is fine: untouched

        class Old(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return dt.datetime(1970, 1, 1, 0, 10)
        with mock.patch.object(service.dt, "datetime", Old), mock.patch.object(service.time, "time", return_value=600):
            self.assertTrue(service.sync_clock(ms))
            self.assertEqual(service.today().year, 2026)
        service.CLOCK["offset"] = 0.0

    def test_map_places_every_problem_and_marks_student_progress(self):
        s = self.svc.add_student({"name": "Ana", "classroom": "4A", "start_level": 2})
        a = self.svc.student_home(s["id"])["current"]
        self.svc.submit(s["id"], {"assignment_id": a["id"], "answers": {p["id"]: "A" for p in a["items"]}})
        topic = a["items"][0]["topic"]
        m = self.svc.map_data(topic, "student", s["id"])          # no layout.json: fallback positions
        self.assertEqual(len(m["nodes"]), len(self.svc.ids_where(topic=topic)))
        n = len(m["nodes"])
        for i, j, _ in m["edges"]:
            self.assertTrue(0 <= i < n and 0 <= j < n)
            self.assertLess(m["nodes"][i][6], m["nodes"][j][6])      # arrows always go up in difficulty
        done = set(m["me"]["solved"]) | set(m["me"]["failed"])
        self.assertEqual(len(done), sum(1 for p in a["items"] if p["topic"] == topic))
        t = self.svc.map_data(topic, "teacher", "profe")
        self.assertIn("class", t)
        self.assertNotIn("me", t)
        p = self.svc.problem_for_student(s["id"], a["items"][0]["id"])
        self.assertNotIn("answer", p)
        self.assertIn(p["status"], ("solved", "failed"))

    def test_add_problem_is_classified_and_searchable(self):
        p = self.svc.add_problem({"text": "Solve the equation: x plus 3 equals 10, find the unknown x", "answer": "c"})
        self.assertEqual(p["topic"], "Algebra")
        self.assertEqual(p["answer"], "C")
        sim = self.svc.similar(p["id"])
        self.assertTrue(sim and sim[0]["topic"] == "Algebra")


class HttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.svc = make_service(cls.tmp.name)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.svc, str(ROOT / "www")))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.svc.db.close()
        cls.tmp.cleanup()

    def client(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def call(self, op, path, body=None, method=None):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode() if body is not None else None,
                                     {"Content-Type": "application/json"}, method=method)
        try:
            with op.open(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_roles_and_flow(self):
        t, s = self.client(), self.client()
        self.assertEqual(self.call(t, "/api/students")[0], 401)
        self.assertEqual(self.call(t, "/api/login", {"role": "teacher", "user": "profe", "password": "no"})[0], 401)
        self.assertEqual(self.call(t, "/api/login", {"role": "teacher", "user": "profe", "password": "pw"})[0], 200)
        code, st = self.call(t, "/api/students", {"name": "Leo", "classroom": "4A", "start_level": 0})
        self.assertEqual(code, 200)
        self.assertEqual(self.call(s, "/api/login", {"role": "student", "code": st["id"].replace("-", "").lower()})[0], 200)
        self.assertEqual(self.call(s, "/api/students")[0], 401)      # students can't use teacher routes
        _, home = self.call(s, "/api/student/home")
        ans = {p["id"]: "A" for p in home["current"]["items"]}
        code, res = self.call(s, "/api/student/submit", {"assignment_id": home["current"]["id"], "answers": ans})
        self.assertEqual(code, 200)
        self.assertEqual(res["status"], "done")
        code, stats = self.call(t, "/api/stats")
        self.assertEqual(stats["answered"], len(ans))
        with urllib.request.urlopen(self.base + "/") as r:
            self.assertIn(b"app.js", r.read())


if __name__ == "__main__":
    unittest.main()
