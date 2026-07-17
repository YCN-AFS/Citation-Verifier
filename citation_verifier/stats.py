"""
Global usage statistics tracker.

Thread-safe JSON file-based counter for tracking total verifications
across all users. Displayed on the hero section as social proof.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_STATS_FILE = Path(__file__).parent.parent / "data" / "stats.json"
_lock = threading.Lock()

_DEFAULT_STATS = {
    "total_sessions": 0,
    "total_references": 0,
    "last_verified_at": None,
}


def _ensure_data_dir():
    """Create data directory if it doesn't exist."""
    _STATS_FILE.parent.mkdir(parents=True, exist_ok=True)


def get_stats() -> dict:
    """Get current global stats (thread-safe)."""
    _ensure_data_dir()
    with _lock:
        if _STATS_FILE.exists():
            try:
                return json.loads(_STATS_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                return dict(_DEFAULT_STATS)
        return dict(_DEFAULT_STATS)


def increment_stats(refs_count: int):
    """Increment global counters after a successful verification (thread-safe)."""
    _ensure_data_dir()
    with _lock:
        stats = dict(_DEFAULT_STATS)
        if _STATS_FILE.exists():
            try:
                stats = json.loads(_STATS_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass

        stats["total_sessions"] = stats.get("total_sessions", 0) + 1
        stats["total_references"] = stats.get("total_references", 0) + refs_count
        stats["last_verified_at"] = datetime.now(timezone.utc).isoformat()

        _STATS_FILE.write_text(
            json.dumps(stats, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
