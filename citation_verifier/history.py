"""
Verification history persistence.

Stores verification sessions in SQLite so users can review past results.
Each session records input preview, result count, summary, and full results JSON.
"""

import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "data" / "history.db"
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Get a thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(_DB_PATH), timeout=5)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                total_refs INTEGER NOT NULL,
                summary_json TEXT NOT NULL,
                has_critical INTEGER NOT NULL,
                input_preview TEXT NOT NULL,
                results_json TEXT NOT NULL
            )
        """)
        _local.conn.commit()
    return _local.conn


def save_session(
    total: int,
    summary: dict,
    has_critical: bool,
    input_text: str,
    results_data: dict,
) -> str:
    """Save a verification session and return its ID."""
    try:
        conn = _get_conn()
        session_id = uuid.uuid4().hex[:8]
        preview = input_text[:300].replace("\n", " ").strip()
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?)",
            (
                session_id,
                time.time(),
                total,
                json.dumps(summary, ensure_ascii=False),
                int(has_critical),
                preview,
                json.dumps(results_data, ensure_ascii=False),
            ),
        )
        conn.commit()
        logger.info("Saved session %s (%d refs)", session_id, total)
        return session_id
    except Exception as e:
        logger.error("Failed to save session: %s", e)
        return ""


def list_sessions(limit: int = 20) -> list:
    """List recent verification sessions (without full results)."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, created_at, total_refs, summary_json, has_critical, input_preview "
            "FROM sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "created_at": r[1],
                "total_refs": r[2],
                "summary": json.loads(r[3]),
                "has_critical": bool(r[4]),
                "input_preview": r[5],
            }
            for r in rows
        ]
    except Exception:
        return []


def get_session(session_id: str) -> Optional[dict]:
    """Retrieve full session results by ID."""
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT results_json FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])
    except Exception:
        return None


def delete_session(session_id: str):
    """Delete a session by ID."""
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
    except Exception as e:
        logger.error("Failed to delete session %s: %s", session_id, e)


def clear_all_sessions():
    """Delete all sessions."""
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM sessions")
        conn.commit()
    except Exception as e:
        logger.error("Failed to clear sessions: %s", e)
