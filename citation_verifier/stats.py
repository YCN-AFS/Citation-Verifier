"""
Global usage statistics tracker.

Thread-safe and multi-process-safe counter for tracking total verifications
across all users. Uses SQLite (WAL mode) to ensure correctness under
Gunicorn multi-worker deployments. Displayed on the hero section as social proof.
"""

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "data" / "stats.db"
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Get a thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(_DB_PATH), timeout=5)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        _local.conn.commit()
    return _local.conn


def _migrate_from_json():
    """One-time migration from legacy stats.json to SQLite."""
    import json
    json_path = _DB_PATH.parent / "stats.json"
    if not json_path.exists():
        return

    try:
        old_stats = json.loads(json_path.read_text(encoding="utf-8"))
        conn = _get_conn()

        # Only migrate if SQLite is empty
        row = conn.execute("SELECT COUNT(*) FROM stats").fetchone()
        if row[0] == 0:
            conn.execute(
                "INSERT OR IGNORE INTO stats (key, value) VALUES (?, ?)",
                ("total_sessions", str(old_stats.get("total_sessions", 0)))
            )
            conn.execute(
                "INSERT OR IGNORE INTO stats (key, value) VALUES (?, ?)",
                ("total_references", str(old_stats.get("total_references", 0)))
            )
            last = old_stats.get("last_verified_at")
            if last:
                conn.execute(
                    "INSERT OR IGNORE INTO stats (key, value) VALUES (?, ?)",
                    ("last_verified_at", last)
                )
            conn.commit()
            logger.info("Migrated stats from JSON to SQLite.")

        # Rename old file so migration doesn't run again
        json_path.rename(json_path.with_suffix(".json.bak"))
    except Exception as e:
        logger.warning("Stats migration failed (non-critical): %s", e)


# Run migration on module load
_migrate_from_json()


def get_stats() -> dict:
    """Get current global stats (multi-process safe via SQLite)."""
    try:
        conn = _get_conn()
        rows = conn.execute("SELECT key, value FROM stats").fetchall()
        result = {r[0]: r[1] for r in rows}
        return {
            "total_sessions": int(result.get("total_sessions", 0)),
            "total_references": int(result.get("total_references", 0)),
            "last_verified_at": result.get("last_verified_at"),
        }
    except Exception:
        return {
            "total_sessions": 0,
            "total_references": 0,
            "last_verified_at": None,
        }


def increment_stats(refs_count: int):
    """Increment global counters after a successful verification (multi-process safe)."""
    try:
        conn = _get_conn()
        # Atomic upsert via INSERT OR REPLACE with subquery
        conn.execute("""
            INSERT INTO stats (key, value) VALUES ('total_sessions',
                CAST((SELECT COALESCE(CAST(value AS INTEGER), 0) FROM stats WHERE key='total_sessions') + 1 AS TEXT)
            )
            ON CONFLICT(key) DO UPDATE SET value =
                CAST(CAST(excluded.value AS INTEGER) AS TEXT)
        """)
        conn.execute("""
            INSERT INTO stats (key, value) VALUES ('total_references',
                CAST((SELECT COALESCE(CAST(value AS INTEGER), 0) FROM stats WHERE key='total_references') + ? AS TEXT)
            )
            ON CONFLICT(key) DO UPDATE SET value =
                CAST(CAST(excluded.value AS INTEGER) AS TEXT)
        """, (refs_count,))
        conn.execute("""
            INSERT OR REPLACE INTO stats (key, value) VALUES ('last_verified_at', ?)
        """, (datetime.now(timezone.utc).isoformat(),))
        conn.commit()
    except Exception as e:
        logger.warning("Stats update error: %s", e)
