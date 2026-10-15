"""
Background verification jobs, persisted in SQLite.

Job state lives in the database (not in process memory) so that any
Gunicorn worker can answer a status poll for a job started by another
worker. A running job whose heartbeat stops (worker killed/restarted)
is reported as failed instead of hanging forever.
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

_DB_PATH = Path(__file__).parent.parent / "data" / "jobs.db"
_local = threading.local()

# A running job with no progress for this long is considered dead.
STALE_AFTER = 300
# Finished jobs are kept this long (results are also stored in history).
KEEP_FOR = 86400


def _get_conn() -> sqlite3.Connection:
    if getattr(_local, "conn", None) is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                status TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                error TEXT,
                result_json TEXT
            )
        """)
        conn.commit()
        _local.conn = conn
    return _local.conn


def create_job(owner: str) -> str:
    conn = _get_conn()
    job_id = uuid.uuid4().hex[:12]
    now = time.time()
    conn.execute(
        "INSERT INTO jobs (id, owner, status, created_at, updated_at) "
        "VALUES (?, ?, 'running', ?, ?)",
        (job_id, owner, now, now),
    )
    conn.commit()
    return job_id


def count_active(owner: str) -> int:
    """Number of the owner's non-stale running jobs."""
    conn = _get_conn()
    return conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE owner = ? AND status = 'running' "
        "AND updated_at > ?",
        (owner, time.time() - STALE_AFTER),
    ).fetchone()[0]


def update_progress(job_id: str, done: int, total: int):
    try:
        conn = _get_conn()
        conn.execute(
            "UPDATE jobs SET done = ?, total = ?, updated_at = ? WHERE id = ?",
            (done, total, time.time(), job_id),
        )
        conn.commit()
    except Exception as e:
        logger.warning("Job progress update failed: %s", e)


def finish(job_id: str, result: dict):
    conn = _get_conn()
    conn.execute(
        "UPDATE jobs SET status = 'done', result_json = ?, updated_at = ?, "
        "done = total WHERE id = ?",
        (json.dumps(result, ensure_ascii=False), time.time(), job_id),
    )
    conn.commit()


def fail(job_id: str, message: str):
    try:
        conn = _get_conn()
        conn.execute(
            "UPDATE jobs SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
            (message, time.time(), job_id),
        )
        conn.commit()
    except Exception as e:
        logger.error("Could not mark job %s failed: %s", job_id, e)


def get_job(job_id: str, owner: str) -> Optional[dict]:
    """Return the owner's job state (including the result once done)."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT status, done, total, updated_at, error, result_json "
        "FROM jobs WHERE id = ? AND owner = ?",
        (job_id, owner),
    ).fetchone()
    if row is None:
        return None
    status, done, total, updated_at, error, result_json = row
    if status == "running" and time.time() - updated_at > STALE_AFTER:
        status, error = "failed", "Job was interrupted (server restarted?). Please retry."
        fail(job_id, error)
    out = {"id": job_id, "status": status, "done": done, "total": total}
    if status == "failed":
        out["error"] = error
    if status == "done" and result_json:
        out["result"] = json.loads(result_json)
    return out


def cleanup(max_age: int = KEEP_FOR) -> int:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM jobs WHERE updated_at < ?", (time.time() - max_age,))
    conn.commit()
    return cur.rowcount
