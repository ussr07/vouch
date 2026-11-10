"""Saved briefs: every finished brief is stored, so it can be reopened by its
own link without spending search credits or model tokens again.

Stored as the same JSON the page receives, in the same SQLite file as the cache.
"""
import json
import re
import secrets
import time
from contextlib import closing

from vouch.cache import _connect

ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")


def _table(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS briefs ("
        " id TEXT PRIMARY KEY, created_at REAL NOT NULL, name TEXT NOT NULL,"
        " kind TEXT NOT NULL, goal TEXT NOT NULL, meeting TEXT NOT NULL,"
        " verified INTEGER NOT NULL, payload TEXT NOT NULL)"
    )


def save(brief: dict) -> str:
    """Store a finished brief and return its new id (12 hex characters)."""
    brief_id = secrets.token_hex(6)
    subject = brief.get("subject", {})
    with closing(_connect()) as conn, conn:
        _table(conn)
        conn.execute(
            "INSERT INTO briefs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (brief_id, time.time(), subject.get("name", ""), subject.get("kind", ""),
             subject.get("goal", ""), subject.get("meeting", ""),
             len(brief.get("stories", [])), json.dumps(brief)),
        )
    return brief_id


def get(brief_id: str) -> dict | None:
    """The saved brief, or None if the id is malformed or unknown."""
    if not ID_PATTERN.match(brief_id or ""):
        return None
    with closing(_connect()) as conn:
        _table(conn)
        row = conn.execute("SELECT payload FROM briefs WHERE id = ?", (brief_id,)).fetchone()
    return json.loads(row[0]) if row else None


def recent(limit: int = 50) -> list[dict]:
    """Newest first: just enough to list them (no stories)."""
    with closing(_connect()) as conn:
        _table(conn)
        rows = conn.execute(
            "SELECT id, created_at, name, kind, goal, meeting, verified FROM briefs"
            " ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 200)),)).fetchall()
    return [{"id": r[0], "created_at": r[1], "name": r[2], "kind": r[3], "goal": r[4],
             "meeting": r[5], "verified": r[6]} for r in rows]
