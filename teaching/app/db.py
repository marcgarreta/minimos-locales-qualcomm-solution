"""One SQLite connection shared by every server thread, used by one thread at a time.

ThreadingHTTPServer answers each request in its own thread, and the calculation checker writes
from another one. A single sqlite3 connection must not be used by two threads at the same
moment: on the board (Python 3.13) parallel requests failed with "bad parameter or other API
misuse", returned no session (the student was sent back to the login page after handing in a
mission), or answered 404/500 by mistake.

SafeDB keeps the sqlite3 API the app uses (execute / executemany / executescript, `with db:`
for a transaction, fetchone / fetchall / iteration / lastrowid) but runs each call under one
re-entrant lock and reads every row before releasing it. The data is small, so serialising
costs nothing noticeable.
"""
import sqlite3
import threading


class Result:
    """The rows of a statement, already read."""

    __slots__ = ("rows", "lastrowid", "rowcount")

    def __init__(self, rows, lastrowid=None, rowcount=-1):
        self.rows, self.lastrowid, self.rowcount = rows, lastrowid, rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


class SafeDB:
    def __init__(self, path):
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()

    def execute(self, sql, args=()):
        with self._lock:
            cur = self._conn.execute(sql, args)
            return Result(cur.fetchall(), cur.lastrowid, cur.rowcount)

    def executemany(self, sql, seq):
        with self._lock:
            cur = self._conn.executemany(sql, seq)
            return Result([], cur.lastrowid, cur.rowcount)

    def executescript(self, script):
        with self._lock:
            self._conn.executescript(script)

    # `with db:` = one transaction, held by one thread until it commits or rolls back
    def __enter__(self):
        self._lock.acquire()
        try:
            self._conn.__enter__()
        except BaseException:
            self._lock.release()
            raise
        return self

    def __exit__(self, *exc):
        try:
            return self._conn.__exit__(*exc)
        finally:
            self._lock.release()

    def close(self):
        with self._lock:
            self._conn.close()
