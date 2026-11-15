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
           "initial_problems": 6, "weekend_problems": 8,
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

    def test_check_locks_the_answer_and_skipped_come_back(self):
        s = self.svc.add_student({"name": "Ana", "classroom": "4A", "start_level": 2})
        a = self.svc.student_home(s["id"])["current"]
        first, second = a["items"][0], a["items"][1]
        right = self.svc.problem(first["id"])["answer"]
        wrong = "A" if right != "A" else "B"
        r = self.svc.check(s["id"], {"assignment_id": a["id"], "problem_id": first["id"], "answer": wrong})
        self.assertEqual((r["correct"], r["answer"]), (False, right))
        r = self.svc.check(s["id"], {"assignment_id": a["id"], "problem_id": first["id"], "answer": right})
        self.assertFalse(r["correct"])                                   # can't change it after seeing red
        home = self.svc.student_home(s["id"])["current"]
        self.assertEqual(home["items"][0]["answer"], right)              # revealed only once checked
        self.assertNotIn("answer", home["items"][1])
        self.svc.check(s["id"], {"assignment_id": a["id"], "problem_id": second["id"], "answer": "C"})
        res = self.svc.submit(s["id"], {"assignment_id": a["id"], "answers": {}})   # the rest skipped
        self.assertEqual(res["result"]["total"], 2)
        self.assertEqual(len(res["result"]["skipped"]), len(a["items"]) - 2)
        nxt = self.svc.student_home(s["id"])["current"]
        pend = [i["id"] for i in nxt["items"] if i["role"] == "pendiente"]
        self.assertEqual(sorted(pend), sorted(res["result"]["skipped"]))
        n = self.svc.db.execute("SELECT COUNT(*) FROM attempts WHERE student_id=?", (s["id"],)).fetchone()[0]
        self.assertEqual(n, 2)                                           # skipped ones aren't graded
        with self.assertRaises(ApiError):                                # nothing answered: can't hand in
            self.svc.submit(s["id"], {"assignment_id": nxt["id"], "answers": {}})

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

    def test_demo_student_has_a_fixed_mission_and_reset_recreates_it(self):
        from app import demo
        from app.service import reset_database
        ids = sorted(self.svc._meta)[:5]
        self.svc.cfg["demo_students"] = True
        self.svc.db.close()
        reset_database(self.svc.cfg["data_dir"])                      # what server.py --reset-demo does
        old = demo.DEMO_MISSION
        demo.DEMO_MISSION = ids                                       # the real ids aren't in the fake bank
        try:
            svc = Service(self.svc.cfg)
            a = svc.student_home("DEM-123")["current"]
            self.assertEqual([p["id"] for p in a["items"]], ids)       # always the same problems, same order
            self.assertEqual(a["title"], "Misión de demostración")
            self.assertEqual(len(svc.list_students()), 6)
            svc.check("DEM-123", {"assignment_id": a["id"], "problem_id": ids[0], "answer": "A"})
            svc.db.close()
            backup = reset_database(svc.cfg["data_dir"])
            self.assertTrue(Path(backup, "app.db").exists())
            svc = Service(self.svc.cfg)                               # fresh again: nothing answered
            a = svc.student_home("DEM-123")["current"]
            self.assertTrue(all(p["given"] is None for p in a["items"]))
            svc.db.close()
        finally:
            demo.DEMO_MISSION = old
            self.svc = Service(self.svc.cfg)                          # tearDown closes it

    def test_bank_problem_shows_text_figure_and_option_crops(self):
        pid = sorted(self.svc._meta)[0]
        self.svc.figures = {pid: {"figure": f"multimodal/{pid}/question.png", "fallback": False,
                                  "options": {L: f"multimodal/{pid}/{L}.png" for L in "ABCDE"},
                                  "texts": {L: f"{L}!" for L in "ABCDE"}, "mode": "diagram_and_option_crops"}}
        p = self.svc.problem(pid)
        self.assertEqual(p["figure"], f"/media/seed/multimodal/{pid}/question.png")
        self.assertEqual(p["option_images"]["C"], f"/media/seed/multimodal/{pid}/C.png")
        self.assertEqual(p["options"]["A"], "A!")                       # the team's OCR text
        self.assertTrue(p["text"])                                      # the statement stays text
        crop = Path(self.svc.seed_dir) / "multimodal" / pid / "question.png"
        crop.parent.mkdir(parents=True)
        crop.write_bytes(b"png")
        self.assertEqual(self.svc.media_path(f"seed/multimodal/{pid}/question.png"), crop)
        for bad in ("seed/../app.db", "app.db", "seed/../../x", "/etc/passwd"):
            self.assertIsNone(self.svc.media_path(bad))

    def test_teacher_photo_goes_through_the_pipeline(self):
        calls = []

        class FakePipeline:
            available = True

            def process(self, pid, data, text, level, answer, out):
                calls.append((pid, text, answer, Path(out).name))
                return {"figure": f"ocr/multimodal/{pid}/question.png", "fallback": False, "options": {},
                        "texts": {L: str(i) for i, L in enumerate("ABCDE")}, "mode": "diagram_with_text_options"}
        self.svc.pipeline = FakePipeline()
        png = "data:image/png;base64," + __import__("base64").b64encode(b"\x89PNG fake").decode()
        p = self.svc.add_problem({"text": "Solve the equation x plus 3 equals 10", "answer": "C", "image": png})
        self.assertEqual(calls, [(p["id"], "Solve the equation x plus 3 equals 10", "C", "ocr")])
        self.assertEqual(p["figure"], f"/media/ocr/multimodal/{p['id']}/question.png")
        self.assertEqual(p["options"]["B"], "1")                        # read from the photo

    @unittest.skipUnless((ROOT / "seed/images/lvl-0_2016_16.png").exists(), "needs the local M3Kang bank")
    def test_real_pipeline_cuts_the_figure(self):
        from app.figures import Pipeline
        pipe = Pipeline(ROOT / "ocr_handoff")
        if not pipe.available:
            self.skipTest(pipe.error)
        data = (ROOT / "seed/images/lvl-0_2016_16.png").read_bytes()
        out = Path(self.tmp.name) / "ocr"
        d = pipe.process("t1", data, "From a rectangle measuring 15 x 9 cm, we cut out a square with a perimeter "
                         "of 8 cm from each vertex. What is the perimeter of the resulting figure?", 0, "A", out)
        self.assertEqual(d["figure"], "ocr/multimodal/t1/question.png")
        self.assertEqual(d["texts"], {"A": "48 cm", "B": "40 cm", "C": "32 cm", "D": "24 cm", "E": "16 cm"})
        from PIL import Image
        self.assertLess(Image.open(out / "multimodal/t1/question.png").width, 400)   # the figure, not the page

    def test_add_problem_is_classified_and_searchable(self):
        p = self.svc.add_problem({"text": "Solve the equation: x plus 3 equals 10, find the unknown x", "answer": "c"})
        self.assertEqual(p["topic"], "Algebra")
        self.assertEqual(p["answer"], "C")
        sim = self.svc.similar(p["id"])
        self.assertTrue(sim and sim[0]["topic"] == "Algebra")


class FakeScorer:
    """Qwen-like tokens (one digit per token); only the 4 of '54' is surprising (7 x 8 = 56)."""
    def __init__(self, text):
        self.text = text

    def prompt(self, problem):
        return "P:"

    def tokens(self, text):
        import re
        return [(i, m.start(), m.end()) for i, m in enumerate(re.finditer(r"\d|[^\d\s]+|\s+", text))]

    def nll(self, prompt, ids):
        t = self.text
        return [9.0 if t[a:b] == "4" and t[a - 1:a] == "5" else 0.1 for _, a, b in self.tokens(t)]


class CheckerTest(unittest.TestCase):
    def test_flags_only_the_wrong_number(self):
        from app import checker
        text = "7 x 8 = 54, y 2,5 + 1 = 3,5 €"
        r = checker.check(FakeScorer(text), {"answer": "A"}, text, threshold=5)
        self.assertEqual([n["text"] for n in r["numbers"]], ["7", "8", "54", "2,5", "1", "3,5"])
        self.assertEqual([n["text"] for n in r["numbers"] if n["flag"]], ["54"])

    def test_off_without_config(self):
        from app import checker
        self.assertFalse(checker.Worker({}, None, None).enabled)
        self.assertFalse(checker.Worker({"checker": {"kind": "none"}}, None, None).enabled)

    def test_explain_a_wrong_answer_runs_in_background(self):
        from app import checker
        tmp = tempfile.TemporaryDirectory()
        svc = make_service(tmp.name)
        try:
            done = threading.Event()
            svc.checker = checker.Worker({"checker": {"kind": "llama", "threshold": 5}}, svc._explanation_job,
                                         lambda *a: (svc._explanation_done(*a), done.set()))
            svc.checker.scorer = FakeScorer("7 x 8 = 54")
            s = svc.add_student({"name": "Eva", "start_level": 1})
            a = svc.student_home(s["id"])["current"]
            p1, p2, p3 = a["items"][:3]
            right = {p["id"]: svc.problem(p["id"])["answer"] for p in (p1, p2)}
            body = lambda pid: {"problem_id": pid, "text": "7 x 8 = 54"}
            with self.assertRaises(ApiError):                     # not answered yet
                svc.add_explanation(s["id"], a["id"], body(p1["id"]))
            svc.check(s["id"], {"assignment_id": a["id"], "problem_id": p1["id"],
                                "answer": "B" if right[p1["id"]] != "B" else "C"})
            svc.check(s["id"], {"assignment_id": a["id"], "problem_id": p2["id"], "answer": right[p2["id"]]})
            with self.assertRaises(ApiError):                     # right answers need no explanation
                svc.add_explanation(s["id"], a["id"], body(p2["id"]))
            r = svc.add_explanation(s["id"], a["id"], body(p1["id"]))   # mission still open: allowed
            self.assertIn(r[p1["id"]]["status"], ("pending", "done"))
            self.assertTrue(done.wait(5))
            ex = svc.explanations(s["id"], a["id"])[p1["id"]]
            self.assertEqual(ex["status"], "done")
            self.assertEqual([n["text"] for n in ex["result"]["numbers"] if n["flag"]], ["54"])
            self.assertEqual(svc.explanations("OTHER", a["id"]), {})   # other students can't read it
        finally:
            svc.db.close()
            tmp.cleanup()


class QwenEmbedderTest(unittest.TestCase):
    """The "qwen" embedder: precomputed bank, live server for new texts, approximation without it."""
    DIM = 16
    TOPIC_AXIS = {"Algebra": 0, "Plane geometry": 1, "Arithmetic": 2}

    def vec_for(self, text):
        """Fake model: one axis per topic, picked from the wording (enough to tell topics apart)."""
        v = [0.01] * self.DIM
        t = text.lower()
        v[0 if ("equation" in t or "unknown" in t) else 1 if ("area" in t or "perimeter" in t) else 2] = 1.0
        n = sum(x * x for x in v) ** 0.5
        return [x / n for x in v]

    def setUp(self):
        from array import array
        self.tmp = tempfile.TemporaryDirectory()
        seed = Path(self.tmp.name) / "seed"
        seed.mkdir()
        fake_seed(seed)
        probs = [json.loads(line) for line in (seed / "problems.jsonl").read_text().splitlines()]
        flat = array("f")
        for p in probs:
            flat.extend(self.vec_for(p["text"]))
        (seed / "emb_test.f32").write_bytes(flat.tobytes())
        (seed / "emb_test.json").write_text(json.dumps({"model": "qwen-test", "dim": self.DIM, "ids": [p["id"] for p in probs]}))
        self.server = None
        self.cfg = {"school_name": "T", "teacher": {"user": "p", "password": "p", "name": "P"}, "portal_ip": "192.168.4.1",
                    "port": 0, "dev": True, "data_dir": str(Path(self.tmp.name) / "data"), "seed_dir": str(seed),
                    "embedder": {"kind": "qwen", "model": "qwen-test", "dim": self.DIM, "bank": "emb_test",
                                 "url": "http://127.0.0.1:9/v1/embeddings"},
                    "classifier": "knn", "initial_problems": 6, "weekend_problems": 8,
                    "max_prerequisites_per_mistake": 2, "levels": 8}

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        self.tmp.cleanup()

    def start_fake_server(self):
        from http.server import BaseHTTPRequestHandler
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                data = json.dumps({"data": [{"embedding": outer.vec_for(body["input"])}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.cfg["embedder"]["url"] = f"http://127.0.0.1:{self.server.server_address[1]}/v1/embeddings"

    def test_without_server_uses_bank_and_approximates_new_texts(self):
        svc = Service(self.cfg)
        self.assertFalse(svc.live)
        self.assertEqual(len(svc.index), 72)                      # the whole bank came precomputed
        r = svc.classify({"text": "Solve the equation: the unknown x plus 3 equals 10"})
        self.assertEqual(r["topic"], "Algebra")
        p = svc.add_problem({"text": "Find the unknown in this equation: 2x = 8", "answer": "B"})
        self.assertEqual(p["topic"], "Algebra")
        row = svc.db.execute("SELECT embedder FROM problems WHERE id=?", (p["id"],)).fetchone()
        self.assertEqual(row[0], "qwen-test~approx")
        svc.db.close()
        # the model server comes back: the approximation is redone with the real model at the next start
        self.start_fake_server()
        svc2 = Service(self.cfg)
        self.assertTrue(svc2.live)
        row = svc2.db.execute("SELECT embedder FROM problems WHERE id=?", (p["id"],)).fetchone()
        self.assertEqual(row[0], "qwen-test")
        svc2.db.close()

    def test_live_server_embeds_new_texts(self):
        self.start_fake_server()
        svc = Service(self.cfg)
        self.assertTrue(svc.live)
        vec, name = svc.embed_text("The area of a square is 36 cm2")
        self.assertEqual(name, "qwen-test")
        self.assertAlmostEqual(vec[1], max(vec))
        svc.db.close()


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

    def test_parallel_requests_keep_the_session(self):
        """Regression: after handing in, the result page asks for 3 things at once while the checker
        saves in the background. The shared SQLite connection used to lose the session (401 -> logout)."""
        tmp = tempfile.TemporaryDirectory()
        svc = make_service(tmp.name)                      # its own server: doesn't touch the other tests' data
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc, str(ROOT / "www")))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        self.addCleanup(tmp.cleanup)
        self.addCleanup(svc.db.close)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        old_base, self.base = self.base, base
        self.addCleanup(setattr, self, "base", old_base)
        s = self.client()
        st = svc.add_student({"name": "Paralelo", "classroom": "4A", "start_level": 1})
        self.assertEqual(self.call(s, "/api/login", {"role": "student", "code": st["id"]})[0], 200)
        _, home = self.call(s, "/api/student/home")
        a = home["current"]
        for p in a["items"]:
            self.call(s, "/api/student/check", {"assignment_id": a["id"], "problem_id": p["id"], "answer": "A"})
        code, res = self.call(s, "/api/student/submit", {"assignment_id": a["id"], "answers": {}})
        self.assertEqual(code, 200)
        cookie = next(c for c in s.handlers if isinstance(c, urllib.request.HTTPCookieProcessor)).cookiejar
        header = "; ".join(f"{c.name}={c.value}" for c in cookie)
        stop, bad = threading.Event(), []

        def writer():                                     # like the checker saving results meanwhile
            while not stop.is_set():
                with svc.lock, svc.db:
                    svc.db.execute("UPDATE students SET xp=xp WHERE id=?", (st["id"],))

        def reader(path):
            for _ in range(15):
                req = urllib.request.Request(self.base + path, headers={"Cookie": header})
                try:
                    with urllib.request.urlopen(req) as r:
                        body = json.loads(r.read())
                        if path == "/api/me" and body.get("role") != "student":
                            bad.append((path, "role", body))
                except urllib.error.HTTPError as e:
                    bad.append((path, e.code))
                except OSError as e:
                    bad.append((path, repr(e)))
        paths = [f"/api/student/results/{a['id']}", f"/api/student/assignments/{a['id']}/explanations",
                 "/api/student/home", "/api/me"] * 2
        w = threading.Thread(target=writer)
        w.start()
        threads = [threading.Thread(target=reader, args=(p,)) for p in paths]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        stop.set()
        w.join()
        self.assertEqual(bad, [])

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
