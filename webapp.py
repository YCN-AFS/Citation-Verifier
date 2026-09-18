#!/usr/bin/env python3
"""
Citation Verifier — Web Application.

A Flask-based web interface for the Automated Citation Verification System.
Provides a visual, interactive UI with side-by-side comparison of
cited text vs ground truth.
"""

import json
import logging
from datetime import datetime

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from citation_verifier.config import Verdict, VerificationResult
from citation_verifier.history import (
    clear_all_sessions,
    delete_session,
    get_session,
    list_sessions,
    save_session,
)
from citation_verifier.stats import get_stats, increment_stats
from citation_verifier.verifier import CitationVerifier

app = Flask(__name__, template_folder="templates", static_folder="static")

# ─── Security: CORS ──────────────────────────────────────────
CORS(app, resources={
    r"/api/*": {
        "origins": ["https://citeguard.giize.com", "http://localhost:5000"],
        "methods": ["GET", "POST", "DELETE"],
        "max_age": 3600,
    }
})

# ─── Security: Rate Limiting ─────────────────────────────────
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"],
    storage_uri="memory://",
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Maximum number of references per request
MAX_REFERENCES = 200


@app.route("/")
@limiter.exempt
def index():
    """Serve the main web interface."""
    return render_template("index.html")


@app.route("/api/stats")
def stats():
    """Return global usage statistics for the hero counter."""
    return jsonify(get_stats())


@app.route("/api/health")
def health():
    """Health check endpoint for monitoring."""
    from citation_verifier.cache import get_cache_stats
    return jsonify({
        "status": "healthy",
        "version": "1.2.0",
        "cache": get_cache_stats(),
        "stats": get_stats(),
    })


@app.route("/api/verify", methods=["POST"])
@limiter.limit("10 per minute")
def verify():
    """
    API endpoint for citation verification.

    Expects JSON body: { "text": "reference text..." }
    Returns JSON with verification results.
    """
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field in request body."}), 400

    text = data["text"].strip()
    if not text:
        return jsonify({"error": "Empty reference text."}), 400

    # Validate encoding — reject non-UTF-8 content
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return jsonify({"error": "Invalid text encoding. UTF-8 required."}), 400

    # Limit input size to prevent abuse (max ~100KB or ~200 references)
    if len(text) > 100_000:
        return jsonify({"error": "Input too large. Maximum 100,000 characters."}), 400

    # Estimate reference count (rough: one per non-empty line or DOI)
    line_count = len([l for l in text.split("\n") if l.strip()])
    if line_count > MAX_REFERENCES:
        return jsonify({
            "error": f"Too many references (~{line_count}). Maximum {MAX_REFERENCES}."
        }), 400

    cross_validate = data.get("cross_validate", True)

    try:
        verifier = CitationVerifier(cross_validate=cross_validate)
        results = verifier.verify_text(text)
        increment_stats(len(results))
        response = _serialize_results(results)
        # Save to history
        save_session(
            total=response["total"],
            summary=response["summary"],
            has_critical=response["has_critical"],
            input_text=text,
            results_data=response,
        )
        return jsonify(response)
    except Exception as e:
        logger.error("Verification error: %s", e, exc_info=True)
        return jsonify({"error": f"Verification failed: {str(e)}"}), 500


def _serialize_results(results: list) -> dict:
    """Serialize verification results for the web API."""
    # Summary counts
    counts = {}
    for v in Verdict:
        count = sum(1 for r in results if r.verdict == v)
        if count > 0:
            counts[v.value] = count

    serialized = []
    for r in results:
        entry = {
            "ref_number": r.reference.ref_number,
            "verdict": r.verdict.value,
            "doi": r.reference.doi,
            "cited_title": r.reference.candidate_title,
            "cited_year": r.reference.year,
            "cited_authors": r.reference.authors_raw,
            "raw_text": r.reference.raw_text,
        }

        if r.ground_truth:
            entry["ground_truth"] = {
                "title": r.ground_truth.title,
                "authors": r.ground_truth.authors[:8],
                "year": r.ground_truth.year,
                "source_journal": r.ground_truth.source_journal,
                "doi": r.ground_truth.doi,
                "api_source": r.ground_truth.api_source,
                "is_retracted": r.ground_truth.is_retracted,
            }

        if r.comparison:
            entry["scores"] = {
                "ratio": round(r.comparison.ratio_score, 1),
                "token_sort": round(r.comparison.token_sort_score, 1),
                "token_set": round(r.comparison.token_set_score, 1),
                "final": round(r.comparison.final_score, 1),
                "year_match": r.comparison.year_match,
            }

        entry["cross_validated"] = r.cross_validated
        if r.error_message:
            entry["error"] = r.error_message

        serialized.append(entry)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(results),
        "summary": counts,
        "has_critical": any(
            r.verdict in (Verdict.MISMATCH, Verdict.DEAD_DOI, Verdict.RETRACTED)
            for r in results
        ),
        "results": serialized,
    }


# ─── History API ──────────────────────────────────────────────

@app.route("/api/history")
def history_list():
    """List recent verification sessions."""
    return jsonify(list_sessions(limit=20))


@app.route("/api/history/<session_id>")
def history_get(session_id):
    """Get full results for a specific session."""
    result = get_session(session_id)
    if result is None:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(result)


@app.route("/api/history/<session_id>", methods=["DELETE"])
def history_delete(session_id):
    """Delete a specific session."""
    delete_session(session_id)
    return jsonify({"ok": True})


@app.route("/api/history", methods=["DELETE"])
def history_clear():
    """Clear all history."""
    clear_all_sessions()
    return jsonify({"ok": True})


# ─── Maintenance API ─────────────────────────────────────────

@app.route("/api/cache/cleanup", methods=["POST"])
@limiter.limit("2 per hour")
def cache_cleanup():
    """Purge expired cache entries and old history sessions."""
    from citation_verifier.cache import cleanup_expired
    from citation_verifier.history import cleanup_old_sessions

    cache_result = cleanup_expired()
    history_result = cleanup_old_sessions()

    return jsonify({
        "cache": cache_result,
        "history": history_result,
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
