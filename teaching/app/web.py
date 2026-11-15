"""HTTP layer: captive-portal redirects, static files, /media and the JSON API."""
import json
import mimetypes
import os
import re
import traceback
from http.server import SimpleHTTPRequestHandler
from urllib.parse import parse_qs, unquote, urlparse

from .service import ApiError

COOKIE = "kp_session"
MAX_BODY = 10 * 1024 * 1024

# (method, regex, role or None, handler(svc, who, match, query, body))
ROUTES = []


def route(method, pattern, role=None):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), role, fn))
        return fn
    return deco


@route("GET", "/api/me")
def _me(s, who, m, q, b):
    return s.me(*who) if who else {"role": None}


@route("GET", "/api/board")
def _board(s, who, m, q, b):
    from .service import board_status
    return board_status(s)


@route("GET", "/api/map")
def _map(s, who, m, q, b):
    if not who:
        raise ApiError(401, "Inicia sesión")
    return s.map_data(q.get("topic", ""), who[0], who[1])


@route("GET", "/api/student/problem/([\w.-]+)", "student")
def _student_problem(s, who, m, q, b):
    return s.problem_for_student(who[1], m.group(1))


@route("GET", "/api/taxonomy")
def _tax(s, who, m, q, b):
    return {"taxonomy": s.taxonomy, "topics": s.topics, "levels": s.cfg["levels"], "school": s.cfg["school_name"]}


@route("GET", "/api/students", "teacher")
def _students(s, who, m, q, b):
    return s.list_students()


@route("POST", "/api/students", "teacher")
def _add_student(s, who, m, q, b):
    return s.add_student(b)


@route("GET", "/api/students/([A-Z0-9-]+)", "teacher")
def _student(s, who, m, q, b):
    return s.student_detail(m.group(1))


@route("DELETE", "/api/students/([A-Z0-9-]+)", "teacher")
def _del_student(s, who, m, q, b):
    s.delete_student(m.group(1))
    return {"ok": True}


@route("GET", "/api/problems", "teacher")
def _problems(s, who, m, q, b):
    return s.list_problems(q.get("topic"), q.get("level"), q.get("q"), q.get("limit", 40), q.get("offset", 0))


@route("POST", "/api/problems", "teacher")
def _add_problem(s, who, m, q, b):
    return s.add_problem(b)


@route("GET", "/api/problems/([\\w.-]+)/similar", "teacher")
def _similar(s, who, m, q, b):
    return s.similar(m.group(1))


@route("GET", "/api/problems/([\\w.-]+)", "teacher")
def _problem(s, who, m, q, b):
    return s.problem(m.group(1))


@route("POST", "/api/classify", "teacher")
def _classify(s, who, m, q, b):
    return s.classify(b)


@route("POST", "/api/extract-options", "teacher")
def _extract(s, who, m, q, b):
    return s.extract_options(b)


@route("GET", "/api/stats", "teacher")
def _stats(s, who, m, q, b):
    return s.stats(q.get("classroom") or None)


@route("GET", "/api/student/home", "student")
def _home(s, who, m, q, b):
    return s.student_home(who[1])


@route("POST", "/api/student/submit", "student")
def _submit(s, who, m, q, b):
    return s.submit(who[1], b)


@route("GET", "/api/student/results/(\\d+)", "student")
def _result(s, who, m, q, b):
    return s.result(who[1], int(m.group(1)))


def make_handler(svc, www):
    cfg = svc.cfg
    portal_url = f"http://{cfg['portal_ip']}/"
    local_hosts = {cfg["portal_ip"], "localhost", "127.0.0.1"}

    class Handler(SimpleHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def __init__(self, *a, **kw):
            super().__init__(*a, directory=www, **kw)

        def log_message(self, fmt, *args):
            if os.environ.get("EDU_QUIET") != "1":
                super().log_message(fmt, *args)

        # ----- captive portal -----
        def _foreign_host(self):
            if cfg["dev"]:
                return False
            host = (self.headers.get("Host") or "").split(":")[0]
            return host not in local_hosts

        def _redirect(self):
            self.send_response(302)
            self.send_header("Location", portal_url)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        # ----- helpers -----
        def _who(self):
            raw = self.headers.get("Cookie") or ""
            for part in raw.split(";"):
                k, _, v = part.strip().partition("=")
                if k == COOKIE:
                    return v, svc.session(v)
            return None, None

        def _json(self, status, obj, cookie=None):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if cookie is not None:
                self.send_header("Set-Cookie", f"{COOKIE}={cookie}; Path=/; HttpOnly; SameSite=Lax"
                                 + ("; Max-Age=0" if cookie == "" else "; Max-Age=2592000"))
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ApiError(413, "Petición demasiado grande")
            raw = self.rfile.read(n) if n else b"{}"
            try:
                return json.loads(raw or b"{}")
            except ValueError:
                raise ApiError(400, "JSON no válido")

        def _api(self, method):
            url = urlparse(self.path)
            q = {k: v[-1] for k, v in parse_qs(url.query).items()}
            token, who = self._who()
            if who:
                svc.touch(token, who[0])
            try:
                body = self._body() if method in ("POST", "PUT") else {}
                if url.path == "/api/login" and method == "POST":
                    tok, me = svc.login(body)
                    return self._json(200, me, cookie=tok)
                if url.path == "/api/logout" and method == "POST":
                    if token:
                        svc.logout(token)
                    return self._json(200, {"ok": True}, cookie="")
                for meth, rx, role, fn in ROUTES:
                    m = rx.match(url.path)
                    if m and meth == method:
                        if role and (not who or who[0] != role):
                            raise ApiError(401, "Inicia sesión")
                        return self._json(200, fn(svc, who, m, q, body))
                raise ApiError(404, "Ruta no encontrada")
            except ApiError as e:
                return self._json(e.status, {"error": e.message})
            except Exception:
                traceback.print_exc()
                return self._json(500, {"error": "Error interno"})

        def _media(self, rel):
            p = svc.media_path(unquote(rel))
            if not p:
                self.send_error(404)
                return
            data = p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(str(p))[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        # ----- verbs -----
        def do_GET(self):
            if self._foreign_host():
                return self._redirect()
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                return self._api("GET")
            if path.startswith("/media/"):
                return self._media(path[len("/media/"):])
            if not os.path.isfile(self.translate_path(path)):
                self.path = "/"            # unknown paths (and OS connectivity checks) -> the app
            return super().do_GET()

        def do_HEAD(self):
            if self._foreign_host():
                return self._redirect()
            return super().do_HEAD()

        def do_POST(self):
            if self._foreign_host():
                return self._redirect()
            return self._api("POST")

        def do_DELETE(self):
            return self._api("DELETE")

    return Handler
