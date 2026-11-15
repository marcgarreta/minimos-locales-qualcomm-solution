"""Business logic and storage (SQLite). The HTTP layer (web.py) only calls methods here."""
import base64
import datetime as dt
import json
import os
import random
import secrets

import threading
import time
from collections import deque
from pathlib import Path

from . import checker as checker_mod
from . import classifier as classifier_mod
from . import embedder as embedder_mod
from . import figures as figures_mod
from . import difficulty as diff
from . import progress, recommender
from .db import SafeDB
from .embedder import EmbedderUnavailable
from .vectors import VectorIndex, from_blob, to_blob

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, classroom TEXT NOT NULL DEFAULT 'Aula 1',
  start_level INTEGER NOT NULL DEFAULT 0, xp INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, last_submit TEXT);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY, role TEXT NOT NULL, user_id TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS problems (
  id TEXT PRIMARY KEY, topic TEXT NOT NULL, subtopic TEXT, level INTEGER NOT NULL,
  text TEXT NOT NULL, answer TEXT NOT NULL, options TEXT NOT NULL DEFAULT '{}', image TEXT,
  source TEXT NOT NULL DEFAULT 'm3kang', auto_topic TEXT, auto_confidence REAL,
  created_at TEXT NOT NULL, embedding BLOB, embedder TEXT);
CREATE INDEX IF NOT EXISTS problems_topic_level ON problems(topic, level);
CREATE TABLE IF NOT EXISTS skills (
  student_id TEXT NOT NULL, topic TEXT NOT NULL, theta REAL NOT NULL, n INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (student_id, topic));
CREATE TABLE IF NOT EXISTS assignments (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, kind TEXT NOT NULL,
  title TEXT NOT NULL, created_at TEXT NOT NULL, due TEXT, status TEXT NOT NULL DEFAULT 'open',
  submitted_at TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS assignment_items (
  assignment_id INTEGER NOT NULL, position INTEGER NOT NULL, problem_id TEXT NOT NULL,
  role TEXT NOT NULL, because TEXT, answer TEXT, correct INTEGER,
  PRIMARY KEY (assignment_id, position));
CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, problem_id TEXT NOT NULL,
  assignment_id INTEGER, answer TEXT, correct INTEGER NOT NULL, topic TEXT NOT NULL,
  level INTEGER NOT NULL, theta_before REAL, theta_after REAL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS attempts_student ON attempts(student_id);
CREATE TABLE IF NOT EXISTS explanations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, assignment_id INTEGER NOT NULL,
  problem_id TEXT NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', result TEXT,
  created_at TEXT NOT NULL, updated_at TEXT);
CREATE INDEX IF NOT EXISTS explanations_assignment ON explanations(assignment_id, problem_id);
"""
MAX_EXPLANATION = 2000

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I
LETTERS = ("A", "B", "C", "D", "E")   # a tuple: "" in "ABCDE" would be True


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


# The board has no battery-backed clock and no internet: after a reboot it may think it is 1970.
# When that happens, the first login corrects it with the browser's time (see sync_clock).
CLOCK = {"offset": 0.0}


def now_dt():
    return dt.datetime.now() + dt.timedelta(seconds=CLOCK["offset"])


def today():
    return now_dt().date()


def now():
    return now_dt().isoformat(timespec="seconds")


def sync_clock(client_ms):
    """Adopt the client's clock only when ours is clearly unset (before 2025)."""
    try:
        client = float(client_ms) / 1000
    except (TypeError, ValueError):
        return False
    if dt.datetime.now().year >= 2025 or client < 1.7e9:
        return False
    CLOCK["offset"] = client - time.time()
    return True


def next_weekend(today=None):
    """Sunday of the coming weekend (next week's if today is already Saturday/Sunday)."""
    today = today or globals()['today']()
    days = 6 - today.weekday()
    if days <= 1:
        days += 7
    return (today + dt.timedelta(days=days)).isoformat()


class Service:
    def __init__(self, cfg, rng=None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.started = time.time()
        self.events = deque(maxlen=20)     # what just happened, for the LED matrix
        self.event_seq = 0
        self.seen = {}                     # session token -> (role, last request time)
        self.lock = threading.RLock()
        self.data_dir = Path(cfg["data_dir"])
        (self.data_dir / "uploads").mkdir(parents=True, exist_ok=True)
        self.seed_dir = Path(cfg["seed_dir"])
        self.db = SafeDB(str(self.data_dir / "app.db"))      # shared by all request threads, one at a time
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(problems)")}
        if "num" not in cols:
            self.db.execute("ALTER TABLE problems ADD COLUMN num INTEGER")    # question number = difficulty
        if "figures" not in cols:
            self.db.execute("ALTER TABLE problems ADD COLUMN figures TEXT")   # teacher photos: figures.describe()
        self.db.execute("PRAGMA journal_mode=WAL")
        self.taxonomy = self._load_taxonomy()
        fp = self.seed_dir / "figures.json"     # the bank's figures and option crops (seed/build_figures.py)
        self.figures = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
        self.pipeline = figures_mod.Pipeline(cfg.get("ocr_handoff_path") or Path(__file__).resolve().parent.parent / "ocr_handoff")
        lp = self.seed_dir / "layout.json"
        self.layout = json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else {"topics": {}}
        self.topics = [t for t in self.taxonomy if t != "Other"]
        self.embedder = embedder_mod.make(cfg)
        self.approx_name = self.embedder.name + "~approx"
        self.live = self.embedder.live or self.embedder.check()
        self._retry_at = 0.0
        # wording-only vectors of the bank, to approximate new texts while the model server is down
        self.hasher = None if self.embedder.live else embedder_mod.HashEmbedder(384)
        self.hash_index = VectorIndex(384)
        self.bank_vecs = self._load_bank_vectors()
        self.index = VectorIndex(self.embedder.dim)
        self._meta = {}
        self._seed_if_empty()
        self._load_index()
        print(f"embeddings: {self.embedder.name} ({'live' if self.live else 'precomputed bank, server not answering'})",
              flush=True)
        self.classifier = classifier_mod.make(cfg, lambda t: self.embed_text(t)[0], self.index, self.get)
        self.first = recommender.RandomRecommender()
        self.checker = checker_mod.Worker(cfg, self._explanation_job, self._explanation_done)
        for r in self.db.execute("SELECT id FROM explanations WHERE status='pending' ORDER BY id"):
            self.checker.submit(r["id"])             # resume work left when the server stopped
        if cfg.get("demo_students") and len(self.index) and \
                not self.db.execute("SELECT COUNT(*) FROM students").fetchone()[0]:
            from . import demo
            demo.create(self)

    # ---------- setup ----------
    def _load_taxonomy(self):
        path = self.seed_dir / "categories_eng.json"
        tax = {}
        if path.exists():
            for c in json.loads(path.read_text(encoding="utf-8")):
                tax.setdefault(c["topic"], set()).add(c["subtopic"])
        return {t: sorted(s) for t, s in sorted(tax.items())}

    def _seed_if_empty(self):
        if self.db.execute("SELECT COUNT(*) FROM problems").fetchone()[0]:
            return
        path = self.seed_dir / "problems.jsonl"
        if not path.exists():
            return
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            p = json.loads(line)
            if p["answer"] not in LETTERS:
                continue
            vec = self.bank_vecs.get(p["id"])          # precomputed; anything else is embedded in _load_index
            rows.append((p["id"], p["topic"], p["subtopic"], p["level"], p["text"], p["answer"],
                         json.dumps(p.get("options") or {}), p.get("image") and "seed/" + p["image"],
                         "m3kang", now(), vec is not None and to_blob(vec) or None,
                         self.embedder.name if vec is not None else None))
        with self.db:
            self.db.executemany(
                "INSERT INTO problems (id, topic, subtopic, level, text, answer, options, image, source,"
                " created_at, embedding, embedder) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        print(f"seeded {len(rows)} problems", flush=True)

    def _load_bank_vectors(self):
        """Precomputed vectors of the bank for this model (seed/<bank>.json + .f32), if any."""
        name = self.cfg["embedder"].get("bank")
        if not name:
            return {}
        meta_p, data_p = self.seed_dir / f"{name}.json", self.seed_dir / f"{name}.f32"
        if not (meta_p.exists() and data_p.exists()):
            return {}
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        if meta["model"] != self.embedder.name or meta["dim"] != self.embedder.dim:
            print(f"ignoring {data_p.name}: it is {meta['model']}/{meta['dim']}, not {self.embedder.name}", flush=True)
            return {}
        from array import array
        flat = array("f")
        flat.frombytes(data_p.read_bytes())
        d = meta["dim"]
        return {pid: flat[i * d:(i + 1) * d] for i, pid in enumerate(meta["ids"])}

    def embed_text(self, text):
        """(vector, model name) for a new text. The model server if it answers; if not, an
        approximation: the similarity-weighted mean of the vectors of the bank problems with the
        closest wording, stored as "<model>~approx" and redone when the server is back."""
        if not self.live and time.time() >= self._retry_at and not self.embedder.live:
            self.live = self.embedder.check()
            self._retry_at = time.time() + 300
        if self.live:
            try:
                return self.embedder.embed(text), self.embedder.name
            except EmbedderUnavailable as e:
                self.live, self._retry_at = False, time.time() + 300
                print(f"embedding server not answering ({e}); approximating new texts", flush=True)
        acc, total = [0.0] * self.embedder.dim, 0.0
        for pid, s in self.hash_index.search(self.hasher.embed(text), k=8):
            v = self.index.vector(pid)
            if v is None or s <= 0:
                continue
            w = s * s
            total += w
            for k, x in enumerate(v):
                acc[k] += w * x
        if not total:
            raise ApiError(503, "El modelo de embeddings no responde")
        n = sum(x * x for x in acc) ** 0.5 or 1.0
        return [x / n for x in acc], self.approx_name

    def _load_index(self):
        stale, fill, pending = [], [], []
        for r in self.db.execute("SELECT id, topic, subtopic, level, num, embedding, embedder, text FROM problems"):
            num = r["num"] if r["num"] is not None else diff.question_number(r["id"])
            if r["num"] is None and num is not None:
                fill.append((num, r["id"]))
            self._meta[r["id"]] = {"topic": r["topic"], "subtopic": r["subtopic"], "level": r["level"], "num": num}
            vec = None
            if r["embedding"] is not None and r["embedder"] == self.embedder.name:
                vec = from_blob(r["embedding"])
            elif r["id"] in self.bank_vecs:                       # model changed: take the precomputed vector
                vec = self.bank_vecs[r["id"]]
                stale.append((to_blob(vec), self.embedder.name, r["id"]))
            elif r["embedding"] is not None and r["embedder"] == self.approx_name and not self.live:
                vec = from_blob(r["embedding"])                   # keep the approximation until the server is back
            if vec is not None:
                self.index.add(r["id"], vec, r["level"], r["topic"])
            else:
                pending.append(r)
            if self.hasher:
                self.hash_index.add(r["id"], self.hasher.embed(r["text"] or r["subtopic"] or ""), r["level"], r["topic"])
        for r in pending:                                         # new model, no precomputed vector
            vec, name = self.embed_text(r["text"] or r["subtopic"] or "")
            self.index.add(r["id"], vec, r["level"], r["topic"])
            stale.append((to_blob(vec), name, r["id"]))
        if stale or fill:
            with self.db:
                self.db.executemany("UPDATE problems SET embedding=?, embedder=? WHERE id=?", stale)
                self.db.executemany("UPDATE problems SET num=? WHERE id=?", fill)
        self.ladder = diff.ladder(((m["level"], m["num"]) for m in self._meta.values()), self.cfg["levels"])
        for m in self._meta.values():
            m["g"] = diff.general(self.ladder, m["level"], m["num"])

    # ---------- bank (used by the recommender) ----------
    def get(self, pid):
        return self._meta[pid]

    def ids_where(self, topic=None, level_min=None, level_max=None):
        return [pid for pid, m in self._meta.items()
                if (topic is None or m["topic"] == topic)
                and (level_min is None or m["level"] >= level_min)
                and (level_max is None or m["level"] <= level_max)]

    # ---------- auth ----------
    def event(self, kind, **data):
        self.event_seq += 1
        self.events.append({"seq": self.event_seq, "kind": kind, "at": time.time(), **data})

    def touch(self, token, role):
        self.seen[token] = (role, time.time())

    def login(self, body):
        if sync_clock(body.get("client_time")):
            print(f"clock corrected from the browser: {now()}", flush=True)
        if body.get("role") == "teacher":
            t = self.cfg["teacher"]
            if body.get("user") != t["user"] or body.get("password") != t["password"]:
                raise ApiError(401, "Usuario o contraseña incorrectos")
            role, uid = "teacher", t["user"]
        else:
            code = (body.get("code") or "").strip().upper().replace(" ", "")
            if len(code) == 6:
                code = code[:3] + "-" + code[3:]
            if not self.db.execute("SELECT 1 FROM students WHERE id=?", (code,)).fetchone():
                raise ApiError(401, "Código de alumno no encontrado")
            role, uid = "student", code
        token = secrets.token_urlsafe(24)
        with self.lock, self.db:
            self.db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (token, role, uid, now()))
        self.touch(token, role)
        self.event("login", role=role)
        return token, self.me(role, uid)

    def session(self, token):
        if not token:
            return None
        r = self.db.execute("SELECT role, user_id FROM sessions WHERE token=?", (token,)).fetchone()
        return (r["role"], r["user_id"]) if r else None

    def logout(self, token):
        with self.lock, self.db:
            self.db.execute("DELETE FROM sessions WHERE token=?", (token,))

    def me(self, role, uid):
        if role == "teacher":
            return {"role": "teacher", "name": self.cfg["teacher"]["name"], "school": self.cfg["school_name"]}
        s = self._student(uid)
        return {"role": "student", "id": s["id"], "name": s["name"], "classroom": s["classroom"],
                "school": self.cfg["school_name"]}

    # ---------- students ----------
    def _student(self, sid):
        r = self.db.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
        if not r:
            raise ApiError(404, "Alumno no encontrado")
        return dict(r)

    def _new_code(self):
        while True:
            c = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            c = c[:3] + "-" + c[3:]
            if not self.db.execute("SELECT 1 FROM students WHERE id=?", (c,)).fetchone():
                return c

    def add_student(self, body, code=None):
        name = (body.get("name") or "").strip()
        if not name:
            raise ApiError(400, "Falta el nombre")
        classroom = (body.get("classroom") or "Aula 1").strip()
        start = int(body.get("start_level") or 0)
        if not 0 <= start < self.cfg["levels"]:
            raise ApiError(400, "Nivel inicial fuera de rango")
        with self.lock, self.db:
            sid = code or self._new_code()
            self.db.execute("INSERT INTO students (id, name, classroom, start_level, created_at) VALUES (?,?,?,?,?)",
                            (sid, name, classroom, start, now()))
            self.db.executemany("INSERT INTO skills VALUES (?,?,?,0)",
                                [(sid, t, progress.initial_theta(start)) for t in self.topics])
            items = self.first.initial(self, start, self.cfg["initial_problems"], self.topics)
            self._create_assignment(sid, "inicial", "Primera misión", next_weekend(), items)
        self.event("student")
        return self.student_detail(sid)

    def delete_student(self, sid):
        with self.lock, self.db:
            for table, col in (("skills", "student_id"), ("attempts", "student_id"), ("sessions", "user_id")):
                self.db.execute(f"DELETE FROM {table} WHERE {col}=?", (sid,))
            ids = [r[0] for r in self.db.execute("SELECT id FROM assignments WHERE student_id=?", (sid,))]
            self.db.executemany("DELETE FROM assignment_items WHERE assignment_id=?", [(i,) for i in ids])
            self.db.execute("DELETE FROM assignments WHERE student_id=?", (sid,))
            self.db.execute("DELETE FROM students WHERE id=?", (sid,))

    def _skills(self, sid):
        return {r["topic"]: (r["theta"], r["n"])
                for r in self.db.execute("SELECT topic, theta, n FROM skills WHERE student_id=?", (sid,))}

    def _class_avg(self, classroom):
        rows = self.db.execute(
            "SELECT k.topic, AVG(k.theta) a, COUNT(*) c FROM skills k JOIN students s ON s.id=k.student_id"
            " WHERE s.classroom=? GROUP BY k.topic", (classroom,)).fetchall()
        return {r["topic"]: r["a"] for r in rows}

    def _streak(self, sid):
        """Consecutive weeks (ISO) with at least one submitted task, ending this or last week."""
        weeks = {dt.date.fromisoformat(r[0][:10]).isocalendar()[:2] for r in self.db.execute(
            "SELECT submitted_at FROM assignments WHERE student_id=? AND submitted_at IS NOT NULL", (sid,))}
        d, streak = today(), 0
        if d.isocalendar()[:2] not in weeks:
            d -= dt.timedelta(days=7)
        while d.isocalendar()[:2] in weeks:
            streak += 1
            d -= dt.timedelta(days=7)
        return streak

    def _topic_view(self, sid, classroom):
        sk, avg = self._skills(sid), self._class_avg(classroom)
        acc = {r["topic"]: (r["ok"], r["n"]) for r in self.db.execute(
            "SELECT topic, SUM(correct) ok, COUNT(*) n FROM attempts WHERE student_id=? GROUP BY topic", (sid,))}
        out = []
        for t in self.topics:
            theta, n = sk.get(t, (0.5, 0))
            ok, tot = acc.get(t, (0, 0))
            out.append({"topic": t, **progress.describe(theta), "answered": n,
                        "accuracy": round(ok / tot, 2) if tot else None,
                        "class_avg": round(avg.get(t, theta), 3)})
        return out

    def student_detail(self, sid):
        s = self._student(sid)
        hist = [dict(r) for r in self.db.execute(
            "SELECT id, kind, title, created_at, due, status, submitted_at, result FROM assignments"
            " WHERE student_id=? ORDER BY id DESC", (sid,))]
        for h in hist:
            h["result"] = json.loads(h["result"]) if h["result"] else None
        tot = self.db.execute("SELECT COUNT(*), COALESCE(SUM(correct),0) FROM attempts WHERE student_id=?",
                              (sid,)).fetchone()
        return {**s, "topics": self._topic_view(sid, s["classroom"]), "streak": self._streak(sid),
                "answered": tot[0], "correct": tot[1], "assignments": hist}

    def list_students(self):
        out = []
        for r in self.db.execute("SELECT id FROM students ORDER BY classroom, name"):
            d = self.student_detail(r["id"])
            d.pop("assignments")
            out.append(d)
        return out

    # ---------- problems ----------
    def _problem_row(self, r, with_answer):
        m = self._meta.get(r["id"], {})
        p = {"id": r["id"], "topic": r["topic"], "subtopic": r["subtopic"], "level": r["level"],
             "num": m.get("num"), "difficulty": m.get("g"),
             "text": r["text"], "options": json.loads(r["options"] or "{}"),
             "image": f"/media/{r['image']}" if r["image"] else None, "source": r["source"]}
        # the statement is shown as text: the picture is only the figure (or the page, as a fallback)
        if r["figures"]:
            fig, base = json.loads(r["figures"]), "/media/"
        else:
            fig, base = (self.figures.get(r["id"]) if r["source"] == "m3kang" else None), "/media/seed/"
        if fig:
            if fig.get("figure"):
                p["figure"] = base + fig["figure"]
                p["figure_fallback"] = bool(fig.get("fallback"))
            if fig.get("options"):
                p["option_images"] = {L: base + f for L, f in fig["options"].items()}
            if len(fig.get("texts") or {}) == 5 and r["source"] == "m3kang":
                p["options"] = fig["texts"]                  # the team's repaired OCR of the options
        elif r["image"]:
            p["figure"] = p["image"]                         # a photo the pipeline couldn't process
        if with_answer:
            p.update(answer=r["answer"], auto_topic=r["auto_topic"], auto_confidence=r["auto_confidence"])
        return p

    def problem(self, pid, with_answer=True):
        r = self.db.execute("SELECT * FROM problems WHERE id=?", (pid,)).fetchone()
        if not r:
            raise ApiError(404, "Problema no encontrado")
        return self._problem_row(r, with_answer)

    def list_problems(self, topic=None, level=None, q=None, limit=40, offset=0):
        where, args = [], []
        if topic:
            where.append("topic=?"); args.append(topic)
        if level not in (None, ""):
            where.append("level=?"); args.append(int(level))
        if q:
            where.append("(text LIKE ? OR id LIKE ?)"); args += [f"%{q}%", f"%{q}%"]
        sql = " WHERE " + " AND ".join(where) if where else ""
        total = self.db.execute("SELECT COUNT(*) FROM problems" + sql, args).fetchone()[0]
        rows = self.db.execute(f"SELECT * FROM problems{sql} ORDER BY source DESC, created_at DESC, id"
                               " LIMIT ? OFFSET ?", args + [int(limit), int(offset)]).fetchall()
        counts = {}
        for r in self.db.execute("SELECT topic, level, COUNT(*) c FROM problems GROUP BY topic, level"):
            counts.setdefault(r["topic"], [0] * self.cfg["levels"])[r["level"]] = r["c"]
        return {"total": total, "items": [self._problem_row(r, True) for r in rows], "counts": counts}

    def similar(self, pid, k=6):
        vec = self.index.vector(pid)
        if vec is None:
            raise ApiError(404, "Problema no encontrado")
        hits = self.index.search(vec, k=k, exclude={pid})
        return [{**self.problem(h), "score": round(s, 3)} for h, s in hits]

    def classify(self, body):
        return self.classifier.classify(body.get("text") or "", body.get("topic") or None)

    @staticmethod
    def _decode_image(data_url):
        if not data_url:
            return None, None
        head, _, b64 = data_url.partition(",")
        ext = "png" if "png" in head else "jpg" if "jp" in head else "webp" if "webp" in head else None
        if not ext:
            raise ApiError(400, "Formato de imagen no soportado (PNG, JPG o WEBP)")
        data = base64.b64decode(b64)
        if len(data) > 6 * 1024 * 1024:
            raise ApiError(400, "La imagen pasa de 6 MB")
        return data, ext

    def extract_options(self, body):
        data, _ = self._decode_image(body.get("image"))
        if not data:
            raise ApiError(400, "Falta la imagen")
        try:
            return self.pipeline.read_options(data)
        except Exception as e:
            return {"available": True, "ok": False, "options": {}, "problems": {"*": str(e)}}

    def add_problem(self, body):
        text = (body.get("text") or "").strip()
        answer = (body.get("answer") or "").strip().upper()
        if not text and not body.get("image"):
            raise ApiError(400, "Añade el enunciado o una foto")
        if answer not in LETTERS:
            raise ApiError(400, "Indica la respuesta correcta (A-E)")
        auto = self.classifier.classify(text, None) if text else {"topic": None, "confidence": 0}
        topic = body.get("topic") or auto["topic"]
        if topic not in self.taxonomy:
            raise ApiError(400, "Tema no válido")
        subtopic = body.get("subtopic") or (auto["subtopic"] if auto["topic"] == topic else None)
        if not subtopic:
            subtopic = self.classifier.classify(text, topic).get("subtopic") or self.taxonomy[topic][0]
        level = body.get("level")
        level = int(auto.get("level") or 0) if level in (None, "") else int(level)
        num = body.get("num")
        num = (auto.get("num") if level == auto.get("level") else None) if num in (None, "") else int(num)
        size = self.ladder["sizes"].get(level, diff.DEFAULT_SIZE)
        num = min(max(int(num), 1), size) if num else (size + 1) // 2
        options = {k: str(v).strip() for k, v in (body.get("options") or {}).items()
                   if k in LETTERS and str(v).strip()}
        data, ext = self._decode_image(body.get("image"))
        with self.lock:
            n = self.db.execute("SELECT COUNT(*) FROM problems WHERE source='profe'").fetchone()[0]
            pid = f"profe-{n + 1:04d}"
            while self.db.execute("SELECT 1 FROM problems WHERE id=?", (pid,)).fetchone():
                n += 1
                pid = f"profe-{n + 1:04d}"
        image, figs = None, None
        if data:
            image = f"uploads/{pid}.{ext}"
            (self.data_dir / image).write_bytes(data)
            if text:                         # the team's OCR: figure without the paragraph, option crops
                try:
                    figs = self.pipeline.process(pid, data, text, level, answer, self.data_dir / "ocr")
                except Exception as e:      # a photo it can't read is still saved and shown as is
                    print(f"figures: {pid}: {type(e).__name__}: {e}", flush=True)
            if figs and not options:
                options = figs["texts"]
        with self.lock, self.db:
            vec, ename = self.embed_text(text or subtopic)
            self.db.execute(
                "INSERT INTO problems (id, topic, subtopic, level, num, text, answer, options, image, source, auto_topic,"
                " auto_confidence, created_at, embedding, embedder, figures) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, topic, subtopic, level, num, text, answer, json.dumps(options), image, "profe",
                 auto.get("topic"), auto.get("confidence"), now(), to_blob(vec), ename,
                 json.dumps(figs) if figs else None))
            if self.hasher:
                self.hash_index.add(pid, self.hasher.embed(text or subtopic), level, topic)
            self._meta[pid] = {"topic": topic, "subtopic": subtopic, "level": level, "num": num,
                               "g": diff.general(self.ladder, level, num)}
            self.index.add(pid, vec, level, topic)
        self.event("problem", topic=topic, level=level)
        return self.problem(pid)

    def media_path(self, rel):
        """Map /media/<rel> to a file: seed/... (read-only bank: multimodal/, images/) or the data dir
        (uploads/, ocr/: teacher photos and their crops). Nothing else is served."""
        rel = rel.replace("\\", "/")
        if ".." in rel.split("/") or rel.startswith("/"):
            return None
        if rel.startswith("seed/"):
            rest = rel[5:]
            cands = [self.seed_dir / rest] if rest.split("/")[0] in ("multimodal", "images") else []
            cands.append(self.seed_dir / "images" / rest)          # older links: /media/seed/<id>.png
        elif rel.split("/")[0] in ("uploads", "ocr"):
            cands = [self.data_dir / rel]
        else:
            return None
        return next((p for p in cands if p.is_file()), None)

    # ---------- assignments ----------
    def _create_assignment(self, sid, kind, title, due, items):
        cur = self.db.execute("INSERT INTO assignments (student_id, kind, title, created_at, due) VALUES (?,?,?,?,?)",
                              (sid, kind, title, now(), due))
        aid = cur.lastrowid
        self.db.executemany(
            "INSERT INTO assignment_items (assignment_id, position, problem_id, role, because) VALUES (?,?,?,?,?)",
            [(aid, i, it["problem_id"], it["role"], it.get("because")) for i, it in enumerate(items)])
        return aid

    def _assignment(self, aid, sid, with_answers=False):
        a = self.db.execute("SELECT * FROM assignments WHERE id=? AND student_id=?", (aid, sid)).fetchone()
        if not a:
            raise ApiError(404, "Tarea no encontrada")
        a = dict(a)
        a["result"] = json.loads(a["result"]) if a["result"] else None
        done = a["status"] == "done"
        a["items"] = []
        for it in self.db.execute("SELECT * FROM assignment_items WHERE assignment_id=? ORDER BY position", (aid,)):
            p = self.problem(it["problem_id"], with_answer=with_answers or done or it["answer"] is not None)
            a["items"].append({**p, "role": it["role"], "because": it["because"],
                               "given": it["answer"], "correct": None if it["correct"] is None else bool(it["correct"])})
        return a

    def student_home(self, sid):
        d = self.student_detail(sid)
        cur = self.db.execute("SELECT id FROM assignments WHERE student_id=? AND status='open' ORDER BY id DESC LIMIT 1",
                              (sid,)).fetchone()
        d["current"] = self._assignment(cur["id"], sid) if cur else None
        last = self.db.execute("SELECT id FROM assignments WHERE student_id=? AND status='done' ORDER BY id DESC LIMIT 1",
                               (sid,)).fetchone()
        d["last_result_id"] = last["id"] if last else None
        return d

    def check(self, sid, body):
        """Check one answer while the mission is open. The first answer is kept: after seeing
        green or red the student can't change it. Grading and levels happen at submit()."""
        aid = int(body.get("assignment_id") or 0)
        pid = body.get("problem_id")
        given = (body.get("answer") or "").strip().upper()[:1]
        if given not in LETTERS:
            raise ApiError(400, "Elige una opción de la A a la E")
        with self.lock, self.db:
            a = self.db.execute("SELECT status FROM assignments WHERE id=? AND student_id=?", (aid, sid)).fetchone()
            if not a:
                raise ApiError(404, "Tarea no encontrada")
            if a["status"] != "open":
                raise ApiError(409, "Esta tarea ya se entregó")
            it = self.db.execute("SELECT position, answer FROM assignment_items WHERE assignment_id=? AND problem_id=?",
                                 (aid, pid)).fetchone()
            if not it:
                raise ApiError(404, "Ese problema no está en tu misión")
            right = self.db.execute("SELECT answer FROM problems WHERE id=?", (pid,)).fetchone()[0]
            if it["answer"] is None:
                self.db.execute("UPDATE assignment_items SET answer=?, correct=? WHERE assignment_id=? AND position=?",
                                (given, int(given == right), aid, it["position"]))
            else:
                given = it["answer"]
        return {"problem_id": pid, "given": given, "answer": right, "correct": given == right}

    # ---------- optional written explanation of a wrong answer + calculation check (background) ----------
    def add_explanation(self, sid, aid, body):
        """Allowed for an answered, wrong item, while the mission is open or after it is submitted."""
        pid = body.get("problem_id") or ""
        text = (body.get("text") or "").strip()
        if not text:
            raise ApiError(400, "Escribe cómo lo resolviste")
        if len(text) > MAX_EXPLANATION:
            raise ApiError(400, f"Máximo {MAX_EXPLANATION} caracteres")
        a = self._assignment(aid, sid)
        item = next((it for it in a["items"] if it["id"] == pid), None)
        if not item:
            raise ApiError(404, "Ese problema no está en tu misión")
        if item["given"] is None:
            raise ApiError(409, "Primero responde el problema")
        if item["correct"]:
            raise ApiError(400, "Solo se explican los problemas fallados")
        status = "pending" if self.checker.enabled else "off"
        with self.lock, self.db:
            self.db.execute("DELETE FROM explanations WHERE student_id=? AND assignment_id=? AND problem_id=?",
                            (sid, aid, pid))
            eid = self.db.execute(
                "INSERT INTO explanations (student_id, assignment_id, problem_id, text, status, created_at)"
                " VALUES (?,?,?,?,?,?)", (sid, aid, pid, text, status, now())).lastrowid
        self.checker.submit(eid)
        return self.explanations(sid, aid)

    def explanations(self, sid, aid):
        rows = self.db.execute("SELECT * FROM explanations WHERE student_id=? AND assignment_id=?", (sid, aid))
        return {r["problem_id"]: {"id": r["id"], "text": r["text"], "status": r["status"],
                                  "result": json.loads(r["result"]) if r["result"] else None,
                                  "created_at": r["created_at"]} for r in rows}

    def _explanation_job(self, eid):
        r = self.db.execute("SELECT problem_id, text FROM explanations WHERE id=?", (eid,)).fetchone()
        if not r:
            raise LookupError(eid)
        return self.problem(r["problem_id"]), r["text"]

    def _explanation_done(self, eid, status, result):
        with self.lock, self.db:
            self.db.execute("UPDATE explanations SET status=?, result=?, updated_at=? WHERE id=?",
                            (status, json.dumps(result), now(), eid))

    def submit(self, sid, body):
        aid = int(body.get("assignment_id") or 0)
        answers = body.get("answers") or {}
        with self.lock, self.db:
            a = self._assignment(aid, sid, with_answers=True)
            if a["status"] != "open":
                raise ApiError(409, "Esta tarea ya se entregó")
            student = self._student(sid)
            skills = self._skills(sid)
            before = {t: th for t, (th, _) in skills.items()}
            xp, mistakes, solved, skipped = 0, [], [], []
            for pos, it in enumerate(a["items"]):
                given = it["given"] or (answers.get(it["id"]) or "").strip().upper()[:1]
                if given not in LETTERS:                  # skipped: no grade, back in the next mission
                    skipped.append(it["id"])
                    continue
                ok = given == it["answer"]
                theta, n = skills.get(it["topic"], (progress.initial_theta(student["start_level"]), 0))
                new_theta, n = progress.update(theta, n, it["level"], ok)
                skills[it["topic"]] = (new_theta, n)
                self.db.execute("UPDATE assignment_items SET answer=?, correct=? WHERE assignment_id=? AND position=?",
                                (given, int(ok), aid, pos))
                self.db.execute(
                    "INSERT INTO attempts (student_id, problem_id, assignment_id, answer, correct, topic, level,"
                    " theta_before, theta_after, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (sid, it["id"], aid, given, int(ok), it["topic"], it["level"], theta, new_theta, now()))
                xp += 2 + (10 if ok else 0) + (5 if ok and it["role"] == "reto" else 0)
                (solved if ok else mistakes).append(it["id"])
            if not solved and not mistakes:
                raise ApiError(400, "Contesta al menos un problema antes de entregar")
            for t, (th, n) in skills.items():
                self.db.execute("INSERT OR REPLACE INTO skills VALUES (?,?,?,?)", (sid, t, th, n))
            # what to do next: prerequisites of each mistake + weekend task
            history = {r[0] for r in self.db.execute(
                "SELECT problem_id FROM attempts WHERE student_id=? AND correct=1", (sid,))}
            prereq = {m: recommender.prerequisites(self, m, self.cfg["max_prerequisites_per_mistake"], history)
                      for m in mistakes}
            topic_theta = {t: th for t, (th, _) in skills.items() if t in self.topics}
            items = [{"problem_id": p, "role": "pendiente"} for p in skipped]
            items += recommender.weekend_task(self, topic_theta, mistakes, history | set(solved) | set(skipped),
                                              max(3, self.cfg["weekend_problems"] - len(skipped)),
                                              self.cfg["max_prerequisites_per_mistake"], self.rng)
            due = next_weekend()
            next_id = self._create_assignment(sid, "finde", "Misión del fin de semana", due, items)
            changes = [{"topic": t, "before": round(before.get(t, th), 3), "after": round(th, 3)}
                       for t, (th, _) in skills.items() if t in self.topics and abs(th - before.get(t, th)) > 1e-9]
            result = {"correct": len(solved), "total": len(solved) + len(mistakes), "skipped": skipped, "xp": xp, "changes": changes,
                      "prerequisites": prereq, "next_assignment": next_id}
            self.db.execute("UPDATE assignments SET status='done', submitted_at=?, result=? WHERE id=?",
                            (now(), json.dumps(result), aid))
            self.db.execute("UPDATE students SET xp=xp+?, last_submit=? WHERE id=?", (xp, now(), sid))
        self.event("submit", correct=len(solved), total=len(solved) + len(mistakes))
        return self.result(sid, aid)

    def result(self, sid, aid):
        a = self._assignment(aid, sid, with_answers=True)
        if a["status"] != "done":
            raise ApiError(409, "Esta tarea aún no se ha entregado")
        pre = {m: [self.problem(p, with_answer=False) for p in ps]
               for m, ps in (a["result"] or {}).get("prerequisites", {}).items()}
        return {**a, "prereq_problems": pre}

    # ---------- 3D map of a topic ----------
    def map_data(self, topic, role, uid):
        """Nodes (shared UMAP position + level), arrows to similar problems one level up,
        and what this student has done. Problems added later (no precomputed position) are
        placed at the weighted mean of their nearest neighbours that have one."""
        if topic not in self.taxonomy:
            raise ApiError(404, "Tema no encontrado")
        lay = self.layout["topics"].get(topic, {"pos": {}, "edges": []})
        pos = dict(lay["pos"])
        ids = sorted((pid for pid, m in self._meta.items() if m["topic"] == topic),
                     key=lambda p: (self._meta[p]["g"], p))
        gs = [(p, self._meta[p]["g"], self._meta[p]["level"]) for p in ids]
        edges = [tuple(e) for e in lay["edges"]]
        for pid in ids:
            if pid in pos:
                continue
            vec = self.index.vector(pid)
            hits = [(h, s) for h, s in self.index.search(vec, k=12, topic=topic, exclude={pid}) if h in lay["pos"]][:5]
            if hits:
                w = sum(max(s, 0.01) for _, s in hits)
                pos[pid] = [sum(lay["pos"][h][k] * max(s, 0.01) for h, s in hits) / w for k in (0, 1)]
            else:
                pos[pid] = [0.0, 0.0]
            g = self._meta[pid]["g"]
            for h, s in self.index.rank(vec, diff.neighbours(gs, g, self._meta[pid]["level"], +1, need=2))[:2]:
                edges.append((pid, h, round(s, 3)))
            for h, s in self.index.rank(vec, diff.neighbours(gs, g, self._meta[pid]["level"], -1, need=2))[:2]:
                edges.append((h, pid, round(s, 3)))
        at = {pid: i for i, pid in enumerate(ids)}
        subs = sorted({self._meta[p]["subtopic"] or "" for p in ids})
        out = {
            "topic": topic, "levels": self.cfg["levels"], "subtopics": subs, "model": self.layout.get("model"),
            "ladder": self.ladder,
            "nodes": [[pid, round(pos[pid][0], 4), round(pos[pid][1], 4), self._meta[pid]["level"],
                       subs.index(self._meta[pid]["subtopic"] or ""), self._meta[pid]["num"], self._meta[pid]["g"]]
                      for pid in ids],
            "edges": [[at[a], at[b], s] for a, b, s in edges if a in at and b in at],
        }
        if role == "student":
            solved, failed, last = set(), set(), {}
            for r in self.db.execute("SELECT problem_id, correct, created_at FROM attempts WHERE student_id=? AND topic=?"
                                     " ORDER BY created_at", (uid, topic)):
                (solved if r["correct"] else failed).add(r["problem_id"])
                last[r["problem_id"]] = r["created_at"]
            failed -= solved
            cur = self.db.execute("SELECT id FROM assignments WHERE student_id=? AND status='open' ORDER BY id DESC LIMIT 1",
                                  (uid,)).fetchone()
            mission = {r[0] for r in self.db.execute("SELECT problem_id FROM assignment_items WHERE assignment_id=?",
                                                     (cur["id"],))} if cur else set()
            order = sorted((p for p in solved | failed if p in at), key=lambda p: last[p])
            out["me"] = {"solved": [at[p] for p in solved if p in at], "failed": [at[p] for p in failed if p in at],
                         "mission": [at[p] for p in mission if p in at], "order": [at[p] for p in order]}
            th = self.db.execute("SELECT theta FROM skills WHERE student_id=? AND topic=?", (uid, topic)).fetchone()
            out["me"]["theta"] = th["theta"] if th else None
        else:
            stats = {r["problem_id"]: (r["n"], r["ok"]) for r in self.db.execute(
                "SELECT problem_id, COUNT(*) n, SUM(correct) ok FROM attempts WHERE topic=? GROUP BY problem_id", (topic,))}
            out["class"] = [[at[p], n, ok] for p, (n, ok) in stats.items() if p in at]
        return out

    def problem_for_student(self, sid, pid):
        p = self.problem(pid, with_answer=False)
        r = self.db.execute("SELECT MAX(correct) ok, COUNT(*) n FROM attempts WHERE student_id=? AND problem_id=?",
                            (sid, pid)).fetchone()
        p["status"] = "solved" if r["ok"] == 1 else "failed" if r["n"] else None
        return p

    # ---------- teacher statistics ----------
    def stats(self, classroom=None):
        rooms = [r[0] for r in self.db.execute("SELECT DISTINCT classroom FROM students ORDER BY classroom")]
        where, args = ("WHERE s.classroom=?", [classroom]) if classroom else ("", [])
        students = [self.student_detail(r[0]) for r in self.db.execute(
            f"SELECT s.id FROM students s {where} ORDER BY s.name", args)]
        topics = []
        for t in self.topics:
            thetas = [next(x["theta"] for x in s["topics"] if x["topic"] == t) for s in students]
            r = self.db.execute(
                f"SELECT COUNT(*) n, COALESCE(SUM(a.correct),0) ok FROM attempts a JOIN students s ON s.id=a.student_id"
                f" {where + ' AND' if where else 'WHERE'} a.topic=?", args + [t]).fetchone()
            topics.append({"topic": t, "avg_theta": round(sum(thetas) / len(thetas), 3) if thetas else None,
                           "min": round(min(thetas), 2) if thetas else None,
                           "max": round(max(thetas), 2) if thetas else None,
                           "answered": r["n"], "accuracy": round(r["ok"] / r["n"], 2) if r["n"] else None})
        hard = [dict(r) for r in self.db.execute(
            f"SELECT a.problem_id id, a.topic, a.level, COUNT(*) n, SUM(1-a.correct) wrong FROM attempts a"
            f" JOIN students s ON s.id=a.student_id {where} GROUP BY a.problem_id HAVING wrong>0"
            f" ORDER BY wrong DESC, n DESC LIMIT 6", args)]
        tot = self.db.execute(
            f"SELECT COUNT(*) n, COALESCE(SUM(a.correct),0) ok FROM attempts a JOIN students s ON s.id=a.student_id {where}",
            args).fetchone()
        for s in students:
            s.pop("assignments")
        return {"classrooms": rooms, "classroom": classroom, "students": students, "topics": topics,
                "hardest": hard, "answered": tot["n"],
                "accuracy": round(tot["ok"] / tot["n"], 2) if tot["n"] else None,
                "bank": len(self.index), "embedder": self.embedder.name + ("" if self.live else " (banco precalculado; textos nuevos aproximados)"), "classifier": self.classifier.name,
                "options_reader": self.pipeline.available}


def env_cfg():
    from .config import load
    return load(os.environ.get("EDU_CONFIG"))


def _wifi_clients(path="/var/lib/misc/dnsmasq.leases"):
    """Devices with a DHCP lease from the board's Wi-Fi (dnsmasq runs in the same container)."""
    try:
        with open(path) as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def board_status(svc):
    """Counters for the LED matrix. No names, no codes: safe to expose without login."""
    t = time.time()
    online = {"student": 0, "teacher": 0}
    for tok, (role, last) in list(svc.seen.items()):
        if t - last < 300:
            online[role] = online.get(role, 0) + 1
    day = today().isoformat()
    r = svc.db.execute("SELECT COUNT(*) n, COALESCE(SUM(correct),0) ok FROM attempts WHERE created_at >= ?",
                       (day,)).fetchone()
    subs = svc.db.execute("SELECT COUNT(*) FROM assignments WHERE submitted_at >= ?", (day,)).fetchone()[0]
    avg = {row["topic"]: row["a"] for row in svc.db.execute("SELECT topic, AVG(theta) a FROM skills GROUP BY topic")}
    return {
        "ok": True, "uptime": round(t - svc.started), "clock": now(),
        "students": svc.db.execute("SELECT COUNT(*) FROM students").fetchone()[0],
        "online_students": online["student"], "online_teachers": online["teacher"],
        "wifi_clients": _wifi_clients(), "submissions_today": subs,
        "answers_today": r["n"], "accuracy_today": round(r["ok"] / r["n"], 2) if r["n"] else None,
        "topics": svc.topics, "topic_avg": [round(avg.get(tp, 0), 2) for tp in svc.topics],
        "bank": len(svc.index), "event_seq": svc.event_seq, "events": list(svc.events)[-5:],
    }


def reset_database(data_dir):
    """Move app.db (and its WAL files) to data/backup/<timestamp>/; the next start seeds a fresh demo.
    Returns the backup folder, or None if there was no database."""
    import shutil
    data = Path(data_dir)
    files = [data / n for n in ("app.db", "app.db-wal", "app.db-shm") if (data / n).exists()]
    if not files:
        return None
    dest = data / "backup" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.move(str(f), str(dest / f.name))
    return str(dest)
