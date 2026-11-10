"""A tiny SQLite cache so repeated identical searches cost no Tavily credits.

Why: the free tier is 1,000 credits a month. During development we rerun the
same searches many times, so we store each response the first time and reuse it.
"""
import hashlib
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "vouch.db"


def _connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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
    with _connect() as conn:
        row = conn.execute(
            "SELECT response, created_at FROM search_cache WHERE key = ?",
            (make_key(params),),
        ).fetchone()
    if row and time.time() - row[1] < max_age_hours * 3600:
        return json.loads(row[0])
    return None


def put(params: dict, response: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO search_cache VALUES (?, ?, ?)",
            (make_key(params), json.dumps(response), time.time()),
        )
