"""A tiny SQLite cache so repeated identical searches cost no Tavily credits.

Why: the free tier is 1,000 credits a month. During development we rerun the
same searches many times, so we store each response the first time and reuse it.
"""
import hashlib
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "vouch.db"
KEEP_DAYS = 7   # rows older than this are deleted; they're past their use by then


def _connect() -> sqlite3.Connection:
    """A connection the caller must close (wrap it in closing()).

    `with sqlite3.connect(...)` only commits; it never closes the connection.
    timeout=10 lets the parallel searches wait briefly for each other's writes.
    """
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS search_cache ("
        " key TEXT PRIMARY KEY, response TEXT NOT NULL, created_at REAL NOT NULL)"
    )
    return conn


def make_key(params: dict) -> str:
    """Same parameters -> same key. sort_keys makes the order irrelevant."""
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()


def get(params: dict, max_age_hours: float = 24):
    """Return a cached response, or None if missing or older than max_age_hours."""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT response, created_at FROM search_cache WHERE key = ?",
            (make_key(params),),
        ).fetchone()
    if row and time.time() - row[1] < max_age_hours * 3600:
        return json.loads(row[0])
    return None


def put(params: dict, response: dict) -> None:
    with closing(_connect()) as conn, conn:   # outer: close; inner: commit
        conn.execute(
            "INSERT OR REPLACE INTO search_cache VALUES (?, ?, ?)",
            (make_key(params), json.dumps(response), time.time()),
        )
        conn.execute("DELETE FROM search_cache WHERE created_at < ?",
                     (time.time() - KEEP_DAYS * 86400,))
