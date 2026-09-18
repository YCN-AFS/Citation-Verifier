"""
DOI-based caching layer for API responses.

Uses SQLite for thread-safe, persistent caching of GroundTruth results.
Dramatically reduces API calls for frequently-verified DOIs (e.g. popular
papers cited by many students).

Default TTL: 7 days — academic metadata rarely changes.
"""

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from .config import GroundTruth

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "data" / "doi_cache.db"
_TTL = 7 * 86400  # 7 days in seconds
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Get a thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(_DB_PATH), timeout=5)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("""
            CREATE TABLE IF NOT EXISTS doi_cache (
                doi TEXT PRIMARY KEY,
                ground_truth TEXT NOT NULL,
                api_source TEXT NOT NULL,
                cached_at REAL NOT NULL
            )
        """)
        _local.conn.commit()
    return _local.conn


def get_cached(doi: str) -> Optional[GroundTruth]:
    """
    Retrieve a cached GroundTruth for a DOI.

    Returns None if not cached or if the cache entry has expired.
    """
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT ground_truth, cached_at FROM doi_cache WHERE doi = ?",
            (doi.lower(),)
        ).fetchone()

        if row is None:
            return None

        gt_json, cached_at = row
        if (time.time() - cached_at) > _TTL:
            # Expired — remove and return None
            conn.execute("DELETE FROM doi_cache WHERE doi = ?", (doi.lower(),))
            conn.commit()
            logger.debug("Cache expired for DOI: %s", doi)
            return None

        data = json.loads(gt_json)
        logger.debug("Cache HIT for DOI: %s", doi)
        return GroundTruth(**data)

    except Exception as e:
        logger.warning("Cache read error for %s: %s", doi, e)
        return None


def set_cached(doi: str, ground_truth: GroundTruth):
    """Store a GroundTruth in the cache."""
    try:
        conn = _get_conn()
        gt_dict = {
            "doi": ground_truth.doi,
            "title": ground_truth.title,
            "authors": ground_truth.authors,
            "year": ground_truth.year,
            "source_journal": ground_truth.source_journal,
            "api_source": ground_truth.api_source,
            "is_retracted": ground_truth.is_retracted,
        }
        conn.execute(
            "INSERT OR REPLACE INTO doi_cache (doi, ground_truth, api_source, cached_at) "
            "VALUES (?, ?, ?, ?)",
            (doi.lower(), json.dumps(gt_dict, ensure_ascii=False),
             ground_truth.api_source, time.time())
        )
        conn.commit()
        logger.debug("Cache SET for DOI: %s", doi)
    except Exception as e:
        logger.warning("Cache write error for %s: %s", doi, e)


def get_cache_stats() -> dict:
    """Return cache statistics for the health endpoint."""
    try:
        conn = _get_conn()
        total = conn.execute("SELECT COUNT(*) FROM doi_cache").fetchone()[0]
        valid = conn.execute(
            "SELECT COUNT(*) FROM doi_cache WHERE (? - cached_at) < ?",
            (time.time(), _TTL)
        ).fetchone()[0]
        return {"total_entries": total, "valid_entries": valid}
    except Exception:
        return {"total_entries": 0, "valid_entries": 0}


def cleanup_expired() -> dict:
    """
    Purge expired cache entries and checkpoint WAL file.

    Should be called periodically (e.g., via /api/cache/cleanup)
    to keep the database compact.

    Returns:
        Dict with cleanup statistics.
    """
    try:
        conn = _get_conn()
        # Count expired entries before deletion
        expired = conn.execute(
            "SELECT COUNT(*) FROM doi_cache WHERE (? - cached_at) > ?",
            (time.time(), _TTL)
        ).fetchone()[0]

        # Delete expired entries
        conn.execute(
            "DELETE FROM doi_cache WHERE (? - cached_at) > ?",
            (time.time(), _TTL)
        )

        # Checkpoint WAL to reduce file size
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()

        logger.info("Cache cleanup: removed %d expired entries", expired)
        return {"expired_removed": expired, "status": "ok"}
    except Exception as e:
        logger.error("Cache cleanup error: %s", e)
        return {"expired_removed": 0, "status": f"error: {e}"}
